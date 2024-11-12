from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, DateTime, Boolean, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from datetime import datetime
from typing import Generator

# Создание базы данных и её подключение
DATABASE_URL = "sqlite:///bot_database.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Функция для получения сессии базы данных
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    telegram_id = Column(String, unique=True, nullable=False)
    referral_count = Column(Integer, default=0)
    referrer_id = Column(Integer, ForeignKey('users.id'), nullable=True)

    referrer = relationship("User", remote_side=[id], backref="referrals")
    payouts = relationship("Payout", back_populates="user")

    def __repr__(self):
        return f"<User(username='{self.username}', telegram_id='{self.telegram_id}')>"

class Referral(Base):
    __tablename__ = 'referrals'

    id = Column(Integer, primary_key=True, index=True)
    referrer_id = Column(Integer, ForeignKey('users.id'))
    referred_id = Column(Integer, ForeignKey('users.id'))
    created_at = Column(DateTime, default=datetime.utcnow)

    referrer = relationship("User", foreign_keys=[referrer_id], backref="referred_users")
    referred_user = relationship("User", foreign_keys=[referred_id])

class Payout(Base):
    __tablename__ = 'payouts'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    amount = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    notified = Column(Boolean, default=False)

    user = relationship("User", back_populates="payouts")

# Создание всех таблиц в базе данных
Base.metadata.create_all(bind=engine)

# Функции работы с пользователями и выплатами
def get_user(session: Session, telegram_id: str) -> User:
    """Получение пользователя по telegram_id"""
    return session.query(User).filter_by(telegram_id=telegram_id).first()

def create_payout(session: Session, user_id: int, amount: float):
    """Создание выплаты для пользователя"""
    payout = Payout(user_id=user_id, amount=amount)
    session.add(payout)
    session.commit()
    return payout

def get_pending_payouts(session: Session):
    """Получение списка новых выплат, по которым не отправлено уведомление"""
    return session.query(Payout).filter_by(notified=False).all()

def mark_payout_as_notified(session: Session, payout_id: int):
    """Обновление статуса выплаты как уведомленной"""
    payout = session.query(Payout).filter_by(id=payout_id).first()
    if payout:
        payout.notified = True
        session.commit()
