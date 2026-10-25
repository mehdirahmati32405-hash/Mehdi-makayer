"""Conversation-aware AI router with persistent memory and safe live bot context."""

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import ai_assistant
import ai_analytics
import ai_memory
import config
import db
from categories import CATEGORIES
from services_content import DUTIES_TEXT
from handlers import AskAIForm, send_welcome

router = Router()


@router.message(CommandStart(), F.chat.type == "private")
async def start_from_ai_router(message: Message, state: FSMContext) -> None:
    """Handle /start before any active AI conversation state can intercept it."""
    await send_welcome(message, state)


def _live_context(user_id: int) -> str:
    """Provide safe, aggregated live data plus operational analytics."""
    stats = db.get_stats()
    period = db.get_period_stats(days=7)
    mine = db.get_reports_by_user(user_id, limit=5)
    my_status = "، ".join(
        f"{db.report_code(r['id'])}: {r['status']}" for r in mine
    ) or "هیچ گزارش ثبت‌شده‌ای ندارد"

    basic = (
        "داده‌های واقعی سامانه در زمان پاسخ‌گویی:\n"
        f"کل گزارش‌ها: {stats['total']}\n"
        f"دریافت‌شده: {stats['received']}\n"
        f"در حال رسیدگی: {stats['in_progress']}\n"
        f"رسیدگی‌شده: {stats['done']}\n"
        f"غیرقابل بررسی: {stats['rejected']}\n"
        f"گزارش‌های ۷ روز اخیر: {period['total']}\n"
        f"رسیدگی‌شده در ۷ روز اخیر: {period['done']}\n"
        f"پرتکرارترین دسته در ۷ روز اخیر: {period['top_category'] or 'نامشخص'} "
        f"({period['top_category_count']} مورد)\n"
        f"آخرین وضعیت گزارش‌های همین شهروند: {my_status}\n"
    )
    analytics = ai_analytics.build_analytics_context(days=30)
    return basic + "\n" + analytics + (
        "\nاین داده‌ها فقط برای پاسخ factual و تحلیل استفاده شوند؛ "
        "اگر داده کافی نیست، حدس زده نشود."
    )


@router.message(Command("newchat"), F.chat.type == "private")
async def new_chat(message: Message, state: FSMContext) -> None:
    ai_memory.clear(message.from_user.id)
    await state.set_state(AskAIForm.waiting_question)
    await message.answer("🧹 گفت‌وگوی قبلی پاک شد. سؤال جدیدتان را بپرسید.")


@router.callback_query(F.data == "menu:ask_ai")
async def open_ai(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AskAIForm.waiting_question)
    if callback.message is not None:
        await callback.message.answer(
            "🤖 دستیار هوشمند آماده است.\n\n"
            "می‌توانید چند سؤال پشت سر هم بپرسید و ربات موضوع گفت‌وگو را حفظ می‌کند.\n"
            "برای شروع یک گفت‌وگوی کاملاً جدید: /newchat"
        )
    await callback.answer()


@router.message(AskAIForm.waiting_question, F.chat.type == "private", F.text, ~F.text.startswith("/"))
async def process_ai_question_with_memory(message: Message, state: FSMContext) -> None:
    question = message.text.strip()
    if not question:
        await message.answer("لطفاً یک سؤال بنویسید.")
        return

    thinking_msg = await message.answer("در حال بررسی تخصصی سؤال شما... ⏳")
    system_prompt = ai_assistant.build_system_prompt(DUTIES_TEXT, list(CATEGORIES.values()))
    history = ai_memory.get_history(message.from_user.id)
    live_context = _live_context(message.from_user.id)

    answer = await ai_assistant.ask_ai(
        question,
        config.DEEPSEEK_API_KEY,
        system_prompt + "\n\n" + live_context,
        history=history,
    )

    if not answer.startswith("متأسفانه در حال حاضر امکان پاسخ‌گویی هوشمند"):
        ai_memory.append_turn(message.from_user.id, question, answer)

    await thinking_msg.edit_text(answer + "\n\n💡 برای شروع گفت‌وگوی جدید: /newchat")
    await state.set_state(AskAIForm.waiting_question)


@router.message(AskAIForm.waiting_question, F.chat.type == "private", F.text, ~F.text.startswith("/"))
async def ai_invalid_with_memory(message: Message) -> None:
    await message.answer("لطفاً سؤال را به‌صورت متن ارسال کنید.")
