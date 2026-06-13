import json
import logging
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

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# === Загрузка прайса ===
def load_prices():
    with open("prices.json", "r", encoding="utf-8") as f:
        return json.load(f)

PRICES = load_prices()

# === Состояния ===
class Order(StatesGroup):
    choosing = State()

# === Хранилище корзин в памяти: {user_id: {flower: qty}} ===
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
    return InlineKeyboardMarkup(inline_keyboard=kb)


def quantity_keyboard(flower):
    options = [1, 5, 10, 20, 50]
    kb = []
    row = []
    for q in options:
        row.append(InlineKeyboardButton(text=f"+{q}", callback_data=f"add:{flower}:{q}"))
    kb.append(row)
    kb.append([InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="back")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def cart_text(user_id):
    cart = get_cart(user_id)
    if not cart:
        return "Корзина пуста.", 0
    lines = []
    total = 0
    for flower, qty in cart.items():
        price = PRICES[flower]["price_per_unit"]
        subtotal = price * qty
        total += subtotal
        lines.append(f"{flower}: {qty} шт × {price} руб = {subtotal} руб")
    lines.append(f"\nИтого: {total} руб")
    return "\n".join(lines), total


def cart_keyboard():
    kb = [
        [InlineKeyboardButton(text="✅ Оформить заказ", callback_data="checkout")],
        [InlineKeyboardButton(text="🗑 Очистить корзину", callback_data="clear")],
        [InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="back")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


@dp.message(Command("start"))
async def cmd_start(message: Message):
    text = (
        "👋 Добро пожаловать!\n\n"
        "Здесь вы можете заказать срезанные цветы оптом.\n"
        "Выберите цветок из списка, чтобы добавить его в корзину."
    )
    await message.answer(text, reply_markup=flowers_keyboard())


@dp.callback_query(F.data == "back")
async def back_to_list(callback: CallbackQuery):
    await callback.message.edit_text(
        "Выберите цветок из списка:", reply_markup=flowers_keyboard()
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("flower:"))
async def choose_flower(callback: CallbackQuery):
    flower = callback.data.split(":", 1)[1]
    info = PRICES[flower]
    text = (
        f"🌸 {flower}\n"
        f"Цена за {info['unit']}: {info['price_per_unit']} руб\n"
        f"Пачка: {info['pack_size']} {info['unit']} = {info['pack_price']} руб\n\n"
        f"Сколько добавить в корзину?"
    )
    await callback.message.edit_text(text, reply_markup=quantity_keyboard(flower))
    await callback.answer()


@dp.callback_query(F.data.startswith("add:"))
async def add_to_cart(callback: CallbackQuery):
    _, flower, qty = callback.data.split(":")
    qty = int(qty)
    cart = get_cart(callback.from_user.id)
    cart[flower] = cart.get(flower, 0) + qty
    await callback.answer(f"Добавлено: {flower} +{qty} шт")


@dp.callback_query(F.data == "cart")
async def show_cart(callback: CallbackQuery):
    text, total = cart_text(callback.from_user.id)
    await callback.message.edit_text(text, reply_markup=cart_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "clear")
async def clear_cart(callback: CallbackQuery):
    carts[callback.from_user.id] = {}
    await callback.message.edit_text("Корзина очищена.", reply_markup=flowers_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "checkout")
async def checkout(callback: CallbackQuery):
    text, total = cart_text(callback.from_user.id)
    if total == 0:
        await callback.answer("Корзина пуста!", show_alert=True)
        return

    final_text = (
        f"{text}\n\n"
        f"📦 Заказ оформлен!\n"
        f"💳 Оплата: при получении / уточнение у продавца.\n\n"
        f"Мы свяжемся с вами для подтверждения деталей доставки и оплаты."
    )
    await callback.message.edit_text(final_text)
    await callback.answer()

    # Очистим корзину после оформления
    carts[callback.from_user.id] = {}


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
