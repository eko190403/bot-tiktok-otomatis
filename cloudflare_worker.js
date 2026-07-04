// cloudflare_worker.js
// Salin seluruh kode ini ke editor Cloudflare Workers Anda

export default {
  async fetch(request, env, ctx) {
    if (request.method !== "POST") {
      return new Response("OK", { status: 200 });
    }

    try {
      const payload = await request.json();
      
      // 1. Tangani Callback Query (Klik Tombol Upload)
      if (payload.callback_query) {
        await handleCallbackQuery(payload.callback_query, env);
      } 
      // 2. Tangani Pesan Teks (Perintah /start atau /generate)
      else if (payload.message && payload.message.text) {
        await handleMessage(payload.message, env);
      }

      return new Response("OK", { status: 200 });
    } catch (err) {
      console.error("Error processing request:", err);
      return new Response("Error: " + err.message, { status: 500 });
    }
  }
};

/**
 * Mengirim pesan ke API Telegram
 */
async function sendTelegram(method, body, env) {
  const token = env.TELEGRAM_BOT_TOKEN;
  const url = `https://api.telegram.org/bot${token}/${method}`;
  return fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
}

/**
 * Memicu GitHub Actions Repository Dispatch
 */
async function triggerGitHub(eventType, clientPayload, env) {
  const repo = env.GH_REPO; // format: username/nama-repo
  const token = env.GH_PAT_TOKEN;
  const url = `https://api.github.com/repos/${repo}/dispatches`;

  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Authorization": `token ${token}`,
      "Accept": "application/vnd.github.v3+json",
      "Content-Type": "application/json",
      "User-Agent": "Cloudflare-Worker"
    },
    body: JSON.stringify({
      event_type: eventType,
      client_payload: clientPayload
    })
  });

  return response.status === 204;
}

/**
 * Tangani perintah teks /start dan /generate
 */
async function handleMessage(message, env) {
  const chatId = message.chat.id;
  const text = message.text.trim();

  if (text.startsWith("/start")) {
    await sendTelegram("sendMessage", {
      chat_id: chatId,
      text: "👋 Halo Vio!\nSaya adalah serverless bot yang berjalan di Cloudflare.\n\nKetik /generate untuk memicu pembuatan video Shorts baru di GitHub Actions.",
      parse_mode: "HTML"
    }, env);
  } 
  
  else if (text.startsWith("/generate")) {
    await sendTelegram("sendMessage", {
      chat_id: chatId,
      text: "🧠 Perintah diterima! Menghubungi API GitHub Actions..."
    }, env);

    const success = await triggerGitHub("telegram_trigger", {
      chat_id: String(chatId),
      user: message.from.username || "Vio"
    }, env);

    if (success) {
      await sendTelegram("sendMessage", {
        chat_id: chatId,
        text: "🚀 <b>Sukses!</b>\nWorkflow GitHub Actions telah berhasil dipicu dan video sedang dirender di Cloud.",
        parse_mode: "HTML"
      }, env);
    } else {
      await sendTelegram("sendMessage", {
        chat_id: chatId,
        text: "❌ <b>Gagal!</b> GitHub menolak permintaan dispatch. Pastikan GH_PAT_TOKEN dan GH_REPO valid."
      }, env);
    }
  }
}

/**
 * Tangani klik tombol inline
 */
async function handleCallbackQuery(callbackQuery, env) {
  const queryId = callbackQuery.id;
  const data = callbackQuery.data;
  const message = callbackQuery.message;
  const chatId = message.chat.id;
  const messageId = message.message_id;

  // Jawab callback query Telegram agar spinner loading berhenti
  await sendTelegram("answerCallbackQuery", { callback_query_id: queryId }, env);

  if (!data || !data.startsWith("pub:")) return;

  const parts = data.split(":");
  if (parts.length < 3) return;

  const platformCode = parts[1]; // "yt" atau "tt"
  const videoId = parts[2];
  const platform = platformCode === "yt" ? "YouTube Shorts" : "TikTok";

  const currentCaption = message.caption || "";

  // 1. Perbarui caption Telegram untuk memberi tahu loading
  await sendTelegram("editMessageCaption", {
    chat_id: chatId,
    message_id: messageId,
    caption: `${currentCaption}\n\n⏳ <b>Memproses publikasi ke ${platform}...</b>`,
    parse_mode: "HTML"
  }, env);

  // 2. Picu repository dispatch di GitHub
  const success = await triggerGitHub("telegram_publish", {
    video_id: videoId,
    platform: platformCode === "yt" ? "youtube" : "tiktok",
    chat_id: String(chatId)
  }, env);

  // 3. Edit pesan dengan status akhir
  if (success) {
    await sendTelegram("editMessageCaption", {
      chat_id: chatId,
      message_id: messageId,
      caption: `${currentCaption}\n\n🚀 <b>Perintah dikirim ke GitHub!</b> Proses pengunggahan ke ${platform} sedang berjalan di cloud.`,
      parse_mode: "HTML"
    }, env);
  } else {
    await sendTelegram("editMessageCaption", {
      chat_id: chatId,
      message_id: messageId,
      caption: `${currentCaption}\n\n❌ <b>Gagal memicu GitHub!</b> Periksa kredensial token/repo di Cloudflare environment variables.`,
      parse_mode: "HTML"
    }, env);
  }
}
