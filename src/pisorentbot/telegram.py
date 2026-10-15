from __future__ import annotations

import html

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from .filtering import target_move_in
from .media import build_banner
from .models import Listing
from .store import ListingStore, callback_token, fingerprint, normalize_street

HELP_TEXT = """<b>PisoRentBot</b>
⭐ Priority area · 📉 Price drop · ⚠️ Borderline total
A/B are door-to-door TfL estimates to Oxford Circus and Shoreditch.
Use Save to retain a home and Hide building to suppress that address."""


def _availability(listing: Listing) -> str:
    if listing.available_from:
        value = listing.available_from.strftime("%d %b")
        flexible = listing.available_from < target_move_in("04-15")
        suffix = "(Check if flexible)" if flexible else "✅"
        return f"{value} {suffix}"
    if "immediate" in listing.availability_text.lower():
        return "Now (Check if flexible)"
    return "Check listing"


def render_card(listing: Listing, index: int, price_drop: bool = False) -> str:
    area = listing.outcode or "London"
    badges = "📉 PRICE DROP · " if price_drop else ""
    badges += "⭐ " if listing.priority else ""
    total = listing.total_monthly_cost or listing.rent_pcm
    warning = " ⚠️" if listing.borderline else ""
    deposit = f"£{listing.deposit:,}" if listing.deposit is not None else "Check listing"
    area_size = f" ({listing.area_sqm} m²)" if listing.area_sqm else ""
    commute_a = listing.commute_a
    commute_b = listing.commute_b
    if not commute_a or not commute_b:
        raise ValueError("Cannot render a listing without both commute estimates")
    links = " · ".join(
        f'<a href="{html.escape(url, quote=True)}">{html.escape(portal)}</a>'
        for portal, url in sorted(
            listing.merged_urls.items(),
            key=lambda item: item[0] != "OpenRent",
        )
    ) or html.escape(listing.portal.value)
    if listing.crime_score is None:
        crime = "⚪ N/A"
    else:
        indicator = "🟢" if listing.crime_score < 34 else "🟡" if listing.crime_score < 67 else "🔴"
        crime = f"{indicator} {listing.crime_score}/100"
    amenity_words = {
        "balcony": "🌿 Balcony",
        "washer": "🧺 Washer",
        "washing machine": "🧺 Washer",
        "dishwasher": "🍽️ Dishwasher",
    }
    amenities = list(
        dict.fromkeys(
            label for word, label in amenity_words.items() if word in listing.searchable_text
        )
    )
    final_line = f"🛡️ Crime: {crime} · 🏠 {links}"
    if amenities:
        final_line += " · " + " · ".join(amenities)
    return "\n".join(
        [
            f'<b>#{index} · {badges}{html.escape(area)} · '
            f'<a href="{html.escape(listing.url, quote=True)}">'
            f"{html.escape(listing.title)}</a></b>",
            f"💷 <b>£{total:,}/mo Est. Total{warning}</b> "
            f"<i>(Rent £{listing.rent_pcm:,} · Tax £{listing.council_tax_cost:,} · "
            f"Bills ~£{listing.utilities_cost:,})</i>",
            f"🛋️ <b>{html.escape(listing.furnishing)}</b> · "
            f"🏢 <b>{html.escape(listing.floor)}</b> · "
            f"🛏️ <b>{listing.bedrooms} Bed</b>{area_size}",
            f"📅 <b>Avail:</b> {_availability(listing)} · 💰 <b>Dep:</b> {deposit} · "
            f"<b>EPC:</b> {html.escape(listing.epc_rating or 'Unknown')}",
            f"🚇 <b>A (Ox. Circus):</b> {commute_a.minutes}m "
            f"<i>({html.escape(commute_a.summary)})</i>",
            f"🚇 <b>B (Shoreditch):</b> {commute_b.minutes}m "
            f"<i>({html.escape(commute_b.summary)})</i>",
            final_line,
        ]
    )


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str, store: ListingStore) -> None:
        self.application = Application.builder().token(token).build()
        self.chat_id = chat_id
        self.store = store
        self.application.add_handler(CommandHandler("help", self.help))
        self.application.add_handler(CallbackQueryHandler(self.callback))

    async def send(
        self,
        client: httpx.AsyncClient,
        listing: Listing,
        index: int,
        price_drop: bool,
    ) -> None:
        key = callback_token(fingerprint(listing))
        street = callback_token(normalize_street(listing.street or listing.title))
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("💾 Save", callback_data=f"save:{key}"),
                    InlineKeyboardButton("🙈 Hide building", callback_data=f"hide:{street}"),
                ]
            ]
        )
        await self.application.bot.send_photo(
            chat_id=self.chat_id,
            photo=await build_banner(client, listing),
            caption=render_card(listing, index, price_drop),
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )

    async def help(self, update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        await update.effective_message.reply_text(HELP_TEXT, parse_mode=ParseMode.HTML)

    async def callback(self, update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        query = update.callback_query
        action, value = query.data.split(":", 1)
        if action == "save":
            self.store.save(value)
            await query.answer("Saved")
        elif action == "hide":
            self.store.hide(value)
            await query.answer("Building hidden")

    def run_polling(self) -> None:
        self.application.run_polling()
