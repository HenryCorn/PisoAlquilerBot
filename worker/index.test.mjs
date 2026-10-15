import assert from "node:assert/strict";
import { test } from "node:test";

import worker from "./src/index.js";

function setup() {
  const sql = [];
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ method: url.split("/").pop(), body: JSON.parse(init.body) });
    return new Response("{}");
  };
  const env = {
    TELEGRAM_BOT_TOKEN: "token",
    TELEGRAM_CHAT_ID: "42",
    TELEGRAM_WEBHOOK_SECRET: "secret",
    DB: {
      prepare: (statement) => ({
        bind: (...params) => ({ run: async () => sql.push({ statement, params }) }),
      }),
    },
  };
  return { env, sql, calls };
}

function post(update, secret = "secret") {
  return new Request("https://worker.example/", {
    method: "POST",
    headers: { "X-Telegram-Bot-Api-Secret-Token": secret },
    body: JSON.stringify(update),
  });
}

const keyboard = [[
  { text: "💾 Save", callback_data: "save:abc" },
  { text: "🙈 Hide building", callback_data: "hide:def" },
]];

test("rejects requests without the webhook secret", async () => {
  const { env, sql } = setup();
  const response = await worker.fetch(post({}, "wrong"), env);
  assert.equal(response.status, 403);
  assert.equal(sql.length, 0);
});

test("hide writes to D1 and flips only that button", async () => {
  const { env, sql, calls } = setup();
  await worker.fetch(post({
    callback_query: {
      id: "q1",
      data: "hide:def",
      message: { message_id: 7, chat: { id: 42 }, reply_markup: { inline_keyboard: keyboard } },
    },
  }), env);
  assert.deepEqual(sql, [{
    statement: "INSERT OR IGNORE INTO hidden_buildings (normalized_street) VALUES (?)",
    params: ["def"],
  }]);
  const edit = calls.find((call) => call.method === "editMessageReplyMarkup");
  assert.deepEqual(edit.body.reply_markup.inline_keyboard[0], [
    keyboard[0][0],
    { text: "↩️ Unhide building", callback_data: "unhide:def" },
  ]);
});

test("ignores buttons pressed in other chats", async () => {
  const { env, sql } = setup();
  await worker.fetch(post({
    callback_query: { id: "q2", data: "save:abc", message: { message_id: 1, chat: { id: 9 } } },
  }), env);
  assert.equal(sql.length, 0);
});
