import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from config import TELEGRAM_BOT_TOKEN, ALLOWED_USER_IDS
from runners import run_claude, run_codex, reset_session

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

async def check_auth(update: Update) -> bool:
    user_id = update.effective_user.id
    if user_id not in ALLOWED_USER_IDS:
        logging.warning(f"Unauthorized access attempt by user {user_id}")
        return False
    return True

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update): return
    await update.message.reply_text(
        "👋 欢迎使用 Server CLI Bot!\n\n"
        "可用命令:\n"
        "/claude <prompt> - 调用 Claude Code\n"
        "/codex <prompt> - 调用 CodeX\n"
        "/reset - 重置当前会话 (开启新会话)\n"
    )

async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update): return
    msg = reset_session(update.effective_chat.id)
    await update.message.reply_text(msg)

async def handle_agent(update: Update, context: ContextTypes.DEFAULT_TYPE, agent_name: str, runner_func):
    if not await check_auth(update): return
    if not context.args:
        await update.message.reply_text(f"请在命令后加上提示词，例如: /{agent_name.lower()} 帮我写一个 Python 脚本")
        return

    prompt = " ".join(context.args)
    chat_id = update.effective_chat.id

    progress_msg = await update.message.reply_text(f"⏳ 正在运行 {agent_name}，请稍候...")

    try:
        success, output = runner_func(chat_id, prompt)
    except Exception as exc:
        logging.exception("%s runner failed", agent_name)
        success = False
        output = f"启动或运行 {agent_name} 时出错: {type(exc).__name__}: {exc}"

    MAX_LENGTH = 4000
    if not output:
        output = "执行完成，但没有返回任何输出。"

    chunks = [output[i:i+MAX_LENGTH] for i in range(0, len(output), MAX_LENGTH)]

    await progress_msg.delete()

    for i, chunk in enumerate(chunks):
        import html
        chunk_escaped = html.escape(chunk)
        if success:
            text = f"✅ <b>{agent_name} 结果 ({i+1}/{len(chunks)}):</b>\n<pre>{chunk_escaped}</pre>"
        else:
            text = f"❌ <b>{agent_name} 失败 ({i+1}/{len(chunks)}):</b>\n<pre>{chunk_escaped}</pre>"

        await update.message.reply_text(text, parse_mode='HTML')

async def claude_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_agent(update, context, "Claude", run_claude)

async def codex_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_agent(update, context, "CodeX", run_codex)

if __name__ == '__main__':
    if not TELEGRAM_BOT_TOKEN:
        logging.error("TELEGRAM_BOT_TOKEN is missing! Please set it in .env file.")
        exit(1)

    if not ALLOWED_USER_IDS:
        logging.warning("ALLOWED_USER_IDS is empty! No one will be able to use this bot.")

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", start_cmd))
    app.add_handler(CommandHandler("reset", reset_cmd))
    app.add_handler(CommandHandler("claude", claude_cmd))
    app.add_handler(CommandHandler("codex", codex_cmd))

    logging.info("Bot is starting...")
    app.run_polling()
