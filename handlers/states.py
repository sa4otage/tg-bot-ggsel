from aiogram.fsm.state import State, StatesGroup


class UserStates(StatesGroup):
    waiting_email = State()
    waiting_order_number = State()


class AdminStates(StatesGroup):
    waiting_mb_email = State()
    waiting_mb_service_name = State()
