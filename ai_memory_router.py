"""Conversation-aware AI router. Loaded before the legacy one-question handler."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import ai_assistant
import ai_memory
import config
from categories import CATEGORIES
from services_content import DUTIES_TEXT
from handlers import AskAIForm

router = Router()


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


@router.message(AskAIForm.waiting_question, F.chat.type == "private", F.text)
async def process_ai_question_with_memory(message: Message, state: FSMContext) -> None:
    question = message.text.strip()
    if not question:
        await message.answer("لطفاً یک سؤال بنویسید.")
        return

    thinking_msg = await message.answer("در حال بررسی تخصصی سؤال شما... ⏳")
    system_prompt = ai_assistant.build_system_prompt(DUTIES_TEXT, list(CATEGORIES.values()))
    history = ai_memory.get_history(message.from_user.id)
    answer = await ai_assistant.ask_ai(
        question,
        config.DEEPSEEK_API_KEY,
        system_prompt,
        history=history,
    )

    # خطاهای API را در حافظه ذخیره نکنیم تا گفت‌وگوی سالم خراب نشود.
    if not answer.startswith("متأسفانه در حال حاضر امکان پاسخ‌گویی هوشمند"):
        ai_memory.append_turn(message.from_user.id, question, answer)

    await thinking_msg.edit_text(
        answer + "\n\n💡 برای شروع گفت‌وگوی جدید: /newchat"
    )
    await state.set_state(AskAIForm.waiting_question)


@router.message(AskAIForm.waiting_question, F.chat.type == "private")
async def ai_invalid_with_memory(message: Message) -> None:
    await message.answer("لطفاً سؤال را به‌صورت متن ارسال کنید.")
