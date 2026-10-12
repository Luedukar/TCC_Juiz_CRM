from sqlalchemy import select

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.models import User
from app.security import hash_password


def main() -> None:
    email = settings.bootstrap_email
    password = settings.bootstrap_password
    if not email or not password:
        raise RuntimeError("Defina BOOTSTRAP_EMAIL e BOOTSTRAP_PASSWORD antes de executar.")
    if len(password) < 12:
        raise RuntimeError("BOOTSTRAP_PASSWORD deve ter pelo menos 12 caracteres.")

    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if db.scalar(select(User.id).where(User.role == "sales_manager")):
            raise RuntimeError("Já existe um gestor; o bootstrap inicial não pode ser repetido.")
        normalized_email = email.lower().strip()
        if db.scalar(select(User.id).where(User.email == normalized_email)):
            raise RuntimeError("Já existe um usuário com esse e-mail.")
        db.add(
            User(
                full_name="Gestor inicial",
                email=normalized_email,
                password_hash=hash_password(password),
                role="sales_manager",
            )
        )
        db.commit()
    print(f"Gestor inicial criado: {normalized_email}")


if __name__ == "__main__":
    main()
