// Telegram webhook for PisoRentBot: answers /help and the Save/Hide buttons
// straight from D1, so they work while the GitHub Actions scraper is idle.

const HELP_TEXT = `<b>PisoRentBot</b>
⭐ Priority area · 📉 Price drop · ⚠️ Borderline total
A/B are door-to-door TfL estimates to Oxford Circus and Shoreditch.
Use Save to retain a home and Hide building to suppress that address.`;

const STATEMENTS = {
  save: "INSERT OR IGNORE INTO saved_homes (fingerprint) VALUES (?)",
  unsave: "DELETE FROM saved_homes WHERE fingerprint = ?",
  hide: "INSERT OR IGNORE INTO hidden_buildings (normalized_street) VALUES (?)",
  unhide: "DELETE FROM hidden_buildings WHERE normalized_street = ?",
};

// action -> [opposite action, new button label, toast text]
const TOGGLES = {
  save: ["unsave", "✅ Saved", "Saved"],
  unsave: ["save", "💾 Save", "Removed from saved"],
  hide: ["unhide", "↩️ Unhide building", "Building hidden"],
  unhide: ["hide", "🙈 Hide building", "Building visible again"],
};

async function telegram(env, method, body) {
  const response = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/${method}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) console.error(method, response.status, await response.text());
}

function fromOwnChat(chat, env) {
  return chat && String(chat.id) === String(env.TELEGRAM_CHAT_ID);
}

async function handleCallback(query, env) {
  const [action, value] = (query.data || "").split(":");
  const message = query.message;
  if (!(action in STATEMENTS) || !value || !fromOwnChat(message?.chat, env)) {
    await telegram(env, "answerCallbackQuery", { callback_query_id: query.id });
    return;
  }
  await env.DB.prepare(STATEMENTS[action]).bind(value).run();
  const [next, label, notice] = TOGGLES[action];
  const keyboard = (message.reply_markup?.inline_keyboard || []).map((row) =>
    row.map((button) =>
      button.callback_data === query.data
        ? { text: label, callback_data: `${next}:${value}` }
        : button,
    ),
  );
  await Promise.all([
    telegram(env, "answerCallbackQuery", { callback_query_id: query.id, text: notice }),
    telegram(env, "editMessageReplyMarkup", {
      chat_id: message.chat.id,
      message_id: message.message_id,
      reply_markup: { inline_keyboard: keyboard },
    }),
  ]);
}

export default {
  async fetch(request, env) {
    if (request.method !== "POST") return new Response("PisoRentBot webhook");
    if (request.headers.get("X-Telegram-Bot-Api-Secret-Token") !== env.TELEGRAM_WEBHOOK_SECRET) {
      return new Response("Forbidden", { status: 403 });
    }
    const update = await request.json();
    if (update.callback_query) {
      await handleCallback(update.callback_query, env);
    } else if (/^\/(help|start)\b/.test(update.message?.text || "") && fromOwnChat(update.message.chat, env)) {
      await telegram(env, "sendMessage", {
        chat_id: update.message.chat.id,
        text: HELP_TEXT,
        parse_mode: "HTML",
      });
    }
    return new Response("ok");
  },
};
