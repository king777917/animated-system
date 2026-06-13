import json
import logging
import re
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import asyncio
import os

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN", "ВСТАВЬ_СЮДА_СВОЙ_ТОКЕН")

# Куда слать уведомления о новых заказах (Telegram ID через запятую, если несколько)
NOTIFY_IDS = [2083351251]

# Username менеджера для кнопки связи (без @)
MANAGER_USERNAME = "flo_garden_23"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


# === Загрузка прайса ===
def load_prices():
    with open("prices.json", "r", encoding="utf-8") as f:
        return json.load(f)


PRICES = load_prices()


class OrderForm(StatesGroup):
    waiting_quantity = State()


# Числительные текстом (1-99, наиболее частые для опта)
WORD_NUMBERS = {
    "один": 1, "одна": 1, "два": 2, "две": 2, "три": 3, "четыре": 4, "пять": 5,
    "шесть": 6, "семь": 7, "восемь": 8, "девять": 9, "десять": 10,
    "одиннадцать": 11, "двенадцать": 12, "тринадцать": 13, "четырнадцать": 14,
    "пятнадцать": 15, "шестнадцать": 16, "семнадцать": 17, "восемнадцать": 18,
    "девятнадцать": 19, "двадцать": 20, "тридцать": 30, "сорок": 40,
    "пятьдесят": 50, "шестьдесят": 60, "семьдесят": 70, "восемьдесят": 80,
    "девяносто": 90, "сто": 100,
}


def parse_quantity(text):
    """Парсит количество упаковок из текста: цифры или числительные текстом."""
    text = text.strip().lower()

    # Просто цифра
    if text.isdigit():
        n = int(text)
        return n if n > 0 else None

    # Составные числительные типа "двадцать пять" или "сорок"
    words = re.findall(r"[а-яё]+", text)
    if not words:
        return None

    total = 0
    found = False
    for w in words:
        if w in WORD_NUMBERS:
            total += WORD_NUMBERS[w]
            found = True

    return total if found and total > 0 else None

# === Хранилище корзин в памяти: {user_id: {flower: packs}} ===
carts = {}


def get_cart(user_id):
    if user_id not in carts:
        carts[user_id] = {}
    return carts[user_id]


def flowers_keyboard():
    kb = []
    for name in PRICES.keys():
        kb.append([InlineKeyboardButton(text=name, callback_data=f"flower:{name}")])
    kb.append([InlineKeyboardButton(text="🧺 Корзина / Итого", callback_data="cart")])
    kb.append([
        InlineKeyboardButton(text="💬 Связаться с менеджером", url=f"https://t.me/{MANAGER_USERNAME}")
    ])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def quantity_keyboard(flower):
    kb = [
        [
            InlineKeyboardButton(text="+1 упак", callback_data=f"add:{flower}:1"),
            InlineKeyboardButton(text="+2 упак", callback_data=f"add:{flower}:2"),
            InlineKeyboardButton(text="+5 упак", callback_data=f"add:{flower}:5"),
        ],
        [InlineKeyboardButton(text="✏️ Указать своё количество", callback_data=f"custom:{flower}")],
        [InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="back")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


def cart_text(user_id):
    cart = get_cart(user_id)
    if not cart:
        return "🧺 Корзина пуста.", 0
    lines = ["🧺 Ваш заказ:\n"]
    total = 0
    for flower, packs in cart.items():
        info = PRICES[flower]
        subtotal = info["pack_price"] * packs
        total += subtotal
        if info["unit"] == "упак":
            lines.append(f"{flower}: {packs} упак × {info['pack_price']}₽ = {subtotal}₽")
        else:
            lines.append(
                f"{flower}: {packs} упак (по {info['pack_size']} {info['unit']}) "
                f"× {info['pack_price']}₽ = {subtotal}₽"
            )
    lines.append(f"\n💰 Итого: {total}₽")
    return "\n".join(lines), total


def cart_keyboard():
    kb = [
        [InlineKeyboardButton(text="✅ Оформить заказ", callback_data="checkout")],
        [InlineKeyboardButton(text="🗑 Очистить корзину", callback_data="clear")],
        [InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="back")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    text = (
        "🌻 Добро пожаловать к поставщикам-фермерам с юга!\n\n"
        "Выращиваем и поставляем с любовью и качеством! 🤗\n\n"
        "⚠️ Заказ возможен только упаковками (поштучно не продаём).\n\n"
        "Выберите позицию из списка ниже, чтобы посмотреть цену и добавить в заказ.\n"
        "Также есть возможность связаться с менеджером, для уточнения деталей доставки 👌🏻"
    )
    await message.answer(text, reply_markup=flowers_keyboard())


@dp.callback_query(F.data == "back")
async def back_to_list(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "🌿 Выберите цветок из списка:", reply_markup=flowers_keyboard()
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("flower:"))
async def choose_flower(callback: CallbackQuery):
    flower = callback.data.split(":", 1)[1]
    info = PRICES[flower]
    if info["unit"] == "упак":
        text = (
            f"{flower}\n"
            f"Цена за упаковку: {info['pack_price']}₽\n\n"
            f"Сколько упаковок добавить в корзину?"
        )
    else:
        text = (
            f"{flower}\n"
            f"Упаковка: {info['pack_size']} {info['unit']} = {info['pack_price']}₽ "
            f"({info['price_per_unit']}₽/{info['unit']})\n\n"
            f"Сколько упаковок добавить в корзину?"
        )
    await callback.message.edit_text(text, reply_markup=quantity_keyboard(flower))
    await callback.answer()


@dp.callback_query(F.data.startswith("add:"))
async def add_to_cart(callback: CallbackQuery):
    _, flower, packs = callback.data.split(":")
    packs = int(packs)
    cart = get_cart(callback.from_user.id)
    cart[flower] = cart.get(flower, 0) + packs
    await callback.answer(f"Добавлено: {flower} +{packs} упак")


@dp.callback_query(F.data.startswith("custom:"))
async def custom_quantity_request(callback: CallbackQuery, state: FSMContext):
    flower = callback.data.split(":", 1)[1]
    await state.update_data(flower=flower)
    await state.set_state(OrderForm.waiting_quantity)
    await callback.message.edit_text(
        f"{flower}\n\n"
        f"Напишите количество упаковок (например: 7 или семь):"
    )
    await callback.answer()


@dp.message(OrderForm.waiting_quantity)
async def custom_quantity_received(message: Message, state: FSMContext):
    data = await state.get_data()
    flower = data.get("flower")

    qty = parse_quantity(message.text)
    if qty is None:
        await message.answer(
            "Не получилось распознать количество 🤔\n"
            "Напишите число (например: 7) или словом (например: семь)."
        )
        return

    cart = get_cart(message.from_user.id)
    cart[flower] = cart.get(flower, 0) + qty
    await state.clear()

    await message.answer(
        f"✅ Добавлено: {flower} +{qty} упак",
        reply_markup=flowers_keyboard()
    )


@dp.callback_query(F.data == "cart")
async def show_cart(callback: CallbackQuery):
    text, total = cart_text(callback.from_user.id)
    await callback.message.edit_text(text, reply_markup=cart_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "clear")
async def clear_cart(callback: CallbackQuery):
    carts[callback.from_user.id] = {}
    await callback.message.edit_text("🗑 Корзина очищена.", reply_markup=flowers_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "checkout")
async def checkout(callback: CallbackQuery):
    text, total = cart_text(callback.from_user.id)
    if total == 0:
        await callback.answer("Корзина пуста!", show_alert=True)
        return

    user = callback.from_user
    username = f"@{user.username}" if user.username else "(нет username)"
    full_name = user.full_name

    final_text = (
        f"{text}\n\n"
        f"📦 Заказ оформлен!\n"
        f"💳 Оплата: при получении / уточнение у продавца.\n\n"
        f"По вопросам — нажмите «Связаться с менеджером» в меню.\n"
        f"Мы свяжемся с вами для подтверждения деталей доставки и оплаты."
    )
    await callback.message.edit_text(final_text)
    await callback.answer()

    # Уведомление менеджеру/владельцу
    notify_text = (
        f"🆕 Новый заказ!\n\n"
        f"От: {full_name} ({username})\n"
        f"Telegram ID: {user.id}\n\n"
        f"{text}"
    )
    for chat_id in NOTIFY_IDS:
        try:
            await bot.send_message(chat_id, notify_text)
        except Exception as e:
            logging.error(f"Не удалось отправить уведомление {chat_id}: {e}")

    # Очистим корзину после оформления
    carts[callback.from_user.id] = {}


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
