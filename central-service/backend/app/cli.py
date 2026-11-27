"""Команды Flask для демонстрации центральной БД."""

import os
import secrets
from datetime import datetime, timezone

import click
from flask import Flask
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from werkzeug.security import generate_password_hash

from .access_requests.models import AccessRequest
from .catalog.models import Camera, EdgeNode, RequestType, Substation
from .db import get_session
from .users.models import User


DEMO_CODE = "DEMO-PS-01"
CAMERA_NAME = "demo-camera-01"
AUTHOR_LOGIN = "demo_seed_author"
TYPE_NAME = "Демонстрационный обход"


def register_commands(app: Flask) -> None:
    @app.cli.command("create-dispatcher")
    @click.argument("login")
    @click.password_option()
    def create_dispatcher(login: str, password: str) -> None:
        """Создать учётную запись диспетчера локального стенда."""
        if not login.strip() or not password:
            raise click.ClickException("Введите логин и пароль.")
        session = get_session()
        with session.begin():
            created = session.scalar(insert(User).values(
                login=login, full_name=login, role="dispatcher",
                password_hash=generate_password_hash(password),
            ).on_conflict_do_nothing(index_elements=[User.login]).returning(User.id))
            if created is None:
                raise click.ClickException("Логин уже занят.")
        click.echo(f"Учётная запись {login} создана.")

    @app.cli.command("seed-demo")
    def seed_demo() -> None:
        """Создать подстанцию, узел, камеру и активную заявку для демонстрации."""
        session = get_session()
        with session.begin():
            # Код подстанции служит меткой атомарно созданного набора.
            station_id = session.scalar(
                insert(Substation)
                .values(code=DEMO_CODE, name="Учебная подстанция", address="Учебный стенд")
                .on_conflict_do_nothing(index_elements=[Substation.code])
                .returning(Substation.id)
            )
            if station_id is None:
                click.echo(f"Подстанция {DEMO_CODE} уже существует. Данные сохранены.")
                camera_ids = session.execute(
                    select(Camera.substation_id, Camera.camera_id)
                    .join(Substation, Camera.substation_id == Substation.id)
                    .where(Substation.code == DEMO_CODE)
                    .order_by(Camera.camera_id)
                ).all()
                for station_id, camera_id in camera_ids:
                    click.echo(f"Камера {station_id}:{camera_id}.")
                return

            if session.scalar(select(User.id).where(User.login == AUTHOR_LOGIN)) is not None:
                raise click.ClickException(f"Логин демонстрационного автора {AUTHOR_LOGIN} занят.")
            author = User(
                login=AUTHOR_LOGIN,
                full_name="Автор демонстрационной заявки",
                password_hash=generate_password_hash(secrets.token_urlsafe(32)),
                role="dispatcher",
                is_blocked=True,
            )
            request_type = session.scalar(select(RequestType).where(RequestType.name == TYPE_NAME))
            if request_type is None:
                request_type = RequestType(name=TYPE_NAME)
                session.add(request_type)

            supplied_key = os.environ.get("DEMO_NODE_API_KEY")
            if supplied_key == "":
                raise click.ClickException("Переменная DEMO_NODE_API_KEY содержит пустой ключ.")
            node_key = supplied_key if supplied_key is not None else secrets.token_urlsafe(32)
            node = EdgeNode(
                substation_id=station_id,
                name="demo-edge-01",
                api_key_hash=generate_password_hash(node_key),
            )
            session.add_all([author, node])
            session.flush()
            camera = Camera(
                camera_id=1,
                name=CAMERA_NAME,
                substation_id=station_id,
                node_id=node.id,
                rtsp_url="rtsp://camera.example.invalid/demo",
            )
            request = AccessRequest(
                substation_id=station_id,
                type_id=request_type.id,
                created_by=author.id,
                responsible="Учебная бригада",
                people_count=1,
                valid_from=datetime(2026, 11, 23, 9, tzinfo=timezone.utc),
                valid_to=datetime(2026, 11, 23, 12, tzinfo=timezone.utc),
                status="active",
            )
            session.add_all([camera, request])
            session.flush()
            camera_id, node_id, request_id = camera.camera_id, node.id, request.id

        click.echo(
            f"Создана подстанция {DEMO_CODE}, узел ID {node_id}, "
            f"камера {station_id}:{camera_id}, заявка ID {request_id}."
        )
        if supplied_key is None:
            click.echo(f"API-ключ демонстрационного узла (показывается один раз): {node_key}")

    @app.cli.command("show-camera")
    @click.argument("substation_id", type=int)
    @click.argument("camera_id", type=int)
    def show_camera(substation_id: int, camera_id: int) -> None:
        """Показать камеру по ID подстанции и номеру камеры."""
        camera = get_session().get(Camera, (substation_id, camera_id))
        if camera is None:
            raise click.ClickException(f"Камера {substation_id}:{camera_id} не найдена.")
        click.echo(f"Камера: {camera.name} ({substation_id}:{camera_id})")
        click.echo(f"Подстанция: {camera.substation.name} ({camera.substation.code})")
        click.echo(f"Узел: {camera.node.name if camera.node else 'не назначен'}")
