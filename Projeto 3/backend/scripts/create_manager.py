"""Cria o primeiro gestor de vendas (bootstrap).

Uso:  python -m scripts.create_manager --name "Maria Silva" --email maria@empresa.com
A senha é pedida de forma interativa (não fica no histórico do shell).
"""
import argparse
import getpass
import sys

from pydantic import ValidationError
from sqlalchemy import select

from app.database import get_sessionmaker
from app.models import User, UserRole
from app.schemas import UserCreate
from app.security import hash_password


def main() -> int:
    parser = argparse.ArgumentParser(description="Cria um usuário gestor de vendas")
    parser.add_argument("--name", required=True)
    parser.add_argument("--email", required=True)
    args = parser.parse_args()

    password = getpass.getpass("Senha (mín. 10 caracteres, letras e números): ")
    if password != getpass.getpass("Confirme a senha: "):
        print("As senhas não conferem.", file=sys.stderr)
        return 1
    try:
        data = UserCreate(name=args.name, email=args.email, password=password, role=UserRole.sales_manager)
    except ValidationError as exc:
        for err in exc.errors():
            print(f"- {err['loc'][-1]}: {err['msg']}", file=sys.stderr)
        return 1

    with get_sessionmaker()() as db:
        if db.scalar(select(User).where(User.email == data.email)):
            print("Já existe um usuário com este e-mail.", file=sys.stderr)
            return 1
        db.add(User(name=data.name, email=data.email, password_hash=hash_password(password), role=data.role))
        db.commit()
    print(f"Gestor {data.email} criado com sucesso.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
