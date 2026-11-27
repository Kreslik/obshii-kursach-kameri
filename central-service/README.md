# Центральный сервис видеомониторинга

Центральный сервис хранит события в PostgreSQL. Узлы передают детекции и изменения состояния камер через Kafka. Веб-интерфейс диспетчера обслуживает Flask.

## Структура проекта

В одной строке после каталога перечислены его файлы. У каждого пакета внутри `backend/app/` также есть `__init__.py`.

```text
central-service/
├── backend/
│   ├── app/
│   │   ├── __init__.py                Фабрика Flask-приложения и регистрация маршрутов
│   │   ├── config.py                  Настройки из переменных окружения
│   │   ├── db.py                      Движок PostgreSQL, сессии и общая база моделей
│   │   ├── cli.py                     Команды seed-demo и show-camera
│   │   ├── auth/                      routes.py, permissions.py, node_keys.py
│   │   ├── users/                     models.py, routes.py
│   │   ├── catalog/                   models.py, routes.py
│   │   ├── node_events/               consumer.py, schemas.py, events.py
│   │   ├── detections/                models.py, service.py, matching.py
│   │   ├── access_requests/           models.py, routes.py, service.py
│   │   ├── alerts/                    models.py, routes.py, service.py, antispam.py
│   │   ├── realtime/                  alerts_socket.py, tickets.py
│   │   ├── monitoring/                heartbeat.py, watchdog.py
│   │   ├── audit/                     models.py, routes.py, service.py
│   │   ├── reports/                   routes.py, queries.py, export.py
│   │   └── storage/                   frames.py
│   ├── migrations/                    env.py, script.py.mako, versions/, README.md
│   ├── alembic.ini                    Конфигурация миграций
│   ├── tests/                         Тесты Flask, миграций PostgreSQL и обмена Kafka
│   ├── pyproject.toml
│   └── Dockerfile                     Образ Flask и Gunicorn
├── frontend/
│   ├── index.html                     Точка входа в интерфейс
│   ├── src/
│   │   ├── app.js                     Навигация между страницами
│   │   ├── styles.css
│   │   ├── api/                       http.js, alertsSocket.js
│   │   ├── pages/                     login.js, dispatcher.js, requests.js,
│   │   │                              admin.js, audit.js, reports.js
│   │   └── components/                cameraGrid.js, alertFeed.js, alertCard.js,
│   │                                  filters.js, recordTable.js
│   └── Dockerfile                     Образ nginx со статикой интерфейса
├── deploy/                            nginx.conf
├── compose.yaml                       Frontend, Flask, migrate, consumer, Kafka, PostgreSQL, Redis и MinIO
├── .env.example                       Имена переменных и локальные параметры
├── .gitignore
└── README.md
```

## Где разрабатывать функции

| Задача | Файлы и границы ответственности |
|---|---|
| Приём события из Kafka | `node_events/schemas.py` разбирает согласованный JSON. `events.py` записывает данные. `consumer.py` читает топики и подтверждает offset после завершения транзакции. |
| Принять решение о тревоге | `alerts/service.py` выбирает заявку и создаёт тревогу для новой детекции. Ограничение `UNIQUE(alerts.detection_id)` действует в PostgreSQL. |
| Показать и обработать тревогу | `realtime/alerts_socket.py` предназначен для оповещений после сохранения тревоги. На клиенте `alertsSocket.js` открывает соединение, `alertFeed.js` и `alertCard.js` отвечают за ленту и карточку. Обработка решения диспетчера относится к `alerts/service.py`, запись действия — к `audit/service.py`. |
| Контроль узла | `monitoring/heartbeat.py` обновляет время связи и статус конкретного узла. Автоматический переход в offline при прекращении heartbeat остаётся задачей для watchdog. |
| Подготовить отчёт | `reports/queries.py` предназначен для расчёта показателей, `reports/export.py` — для формирования CSV и XLSX, `frontend/src/pages/reports.js` — для страницы аналитики. |

## Запуск центра

Команды ниже выполняются в PowerShell из `central-service`. При первом запуске скопируйте `.env.example` в `.env`, задайте `POSTGRES_PASSWORD`, `MINIO_ROOT_PASSWORD` (от восьми символов) и `JWT_SECRET_KEY`. Для веб-интерфейса нужны `deploy/tls/localhost.crt` и `deploy/tls/localhost.key`. На новом стенде их можно создать локально.

```powershell
New-Item -ItemType Directory -Force deploy/tls
openssl req -x509 -newkey rsa:2048 -nodes -days 365 -subj "/CN=localhost" -addext "subjectAltName=DNS:localhost,IP:127.0.0.1" -keyout deploy/tls/localhost.key -out deploy/tls/localhost.crt
```

Для существующей БД перед обновлением сохраните резервную копию и проверьте её восстановлением в отдельную БД. При старте `migrate` выполняет `alembic upgrade head`, затем запускаются Flask и consumer. В ревизии 0006 удаляется `detections.is_alert`. [Миграции](backend/migrations/README.md) · [ER-диаграмма](../БД%20центра.md)

```powershell
docker compose up -d --build --wait
docker compose ps
docker compose exec backend alembic current
docker compose logs --tail 20 consumer
```

Веб-интерфейс доступен на `https://localhost:8443/`, проверка Flask — `GET /api/v1/health`. Для стенда, которому нужны только события, достаточно `docker compose up -d --build consumer`. Демонстрационные данные загружаются отдельно. В выводе `seed-demo` пара `1:1` означает подстанцию № 1 и камеру № 1. Для другой пары подставьте свои значения.

```powershell
docker compose exec backend flask --app app seed-demo
docker compose exec backend flask --app app show-camera 1 1
```

## Панель диспетчера на локальном стенде

После запуска центра создайте диспетчера. Команда запросит пароль и подтверждение. При повторном запуске существующая учётная запись сохраняется.

```powershell
docker compose exec backend flask --app app create-dispatcher operator
```

Откройте `https://localhost:8443/` и войдите. При действующей сессии приложение сразу открывает панель. Сессия действует восемь часов, хранится в Redis и завершается кнопкой «Выйти». Для панели подходят роли `dispatcher` и `admin`.

| Маршрут | Назначение |
|---|---|
| `POST /api/v1/auth/login` | JSON с полями `login`, `password`. Возвращает профиль и устанавливает защищённую HttpOnly cookie |
| `GET /api/v1/auth/session` | Профиль текущего пользователя или 401 |
| `POST /api/v1/auth/logout` | JSON `{}`. Завершает сессию |
| `GET /api/v1/alerts`, `GET /api/v1/detections` | Постраничные списки. Необязательные параметры `substation_id`, `page` (от 1), `per_page` (1–100, по умолчанию 20). Формат ответа `{items, page, per_page, has_more}` |
| `GET /api/v1/catalog/equipment` | Подстанции с узлами, временем последнего heartbeat и камерами |
| `GET /api/v1/requests` | Список заявок с названием подстанции. Требуется сессия диспетчера или администратора |
| `/ws/alerts` | WebSocket. Проверяет cookie и Origin страницы. После подтверждения подписки Redis отправляет `ready`, затем уведомления об изменениях |

В JSON номера тревог и детекций передаются десятичными строками для точной передачи PostgreSQL `BIGINT`. В ленте это поля `id` и `detection_id`, в таблице детекций — `id` и `alert_id`, а в уведомлении WebSocket с типом `alert` — `id`. При отсутствии связанной тревоги `alert_id` равен `null`. Номера подстанций, камер и заявок передаются числами. Сервер сортирует по времени и числовому ID до пагинации.

Consumer сначала фиксирует событие в PostgreSQL, затем публикует короткое уведомление в Redis. Панель автоматически перечитывает данные по выбранной подстанции. При восстановлении связи и раз в минуту она сверяется с API, в том числе на случай пропуска уведомления. Решение по детекции берётся из сохранённых связей. Оба времени в карточке тревоги показаны в часовом поясе Москвы.

### Как проверить страницу «Заявки»

Из каталога `central-service` запустите локальный стенд и загрузите демонстрационную заявку. Для первого входа создайте диспетчера командой из раздела выше.

```powershell
docker compose up -d --build --wait
docker compose exec backend flask --app app seed-demo
```

Откройте `https://localhost:8443/`, войдите и нажмите «Заявки». Введите в поиск «Учебная бригада», выберите «Учебная подстанция», статус активной заявки и период с 23.11.2026 по 23.11.2026. Строка демонстрационной заявки должна остаться в таблице. Замените поиск на заведомо отсутствующее имя, чтобы увидеть пустой результат. Чтобы проверить отказ API в браузере, откройте загруженный список, включите режим Offline в инструментах разработчика и измените фильтр. Должны сохраниться прежние строки и появиться кнопка повтора. Верните соединение и повторите запрос.

API принимает `q` (фрагмент имени ответственного, названия подстанции или точный номер заявки), `substation_id`, `status` (`pending`, `active`, `closed`, `rejected`), `date_from` и `date_to` в формате `YYYY-MM-DD`. Заявка попадает в выборку, если срок её действия пересекает указанные календарные дни по Москве. Можно указать только одну границу. Удалённые заявки исключаются. Сортировка идёт по началу действия от позднего к раннему, при совпадении — по убыванию номера. Параметры `page` и `per_page` и формат ответа совпадают с лентой тревог.

Для проверки неполной даты введите только день или месяц и смените статус. Форма должна указать поле с ошибкой и сохранить показанные строки. На выборке с тремя страницами перейдите на «Далее» клавишей Tab и дважды нажмите Enter после загрузки очередной страницы. На последней странице фокус должен перейти на «Назад».

На тестовом стенде следующая команда проверяет фильтры, границы дат и числового поиска, доступ без сессии и несколько страниц на данных во временной схеме PostgreSQL.

```powershell
$testsDir = (Resolve-Path backend/tests).Path
docker compose run --rm --no-deps -e TEST_POSTGRES=1 --volume "${testsDir}:/tests:ro" backend python -m unittest discover -s /tests -p test_request_list.py -v
```

### Как воспроизвести две детекции и одну тревогу

1. На тестовом стенде войдите в панель и оставьте фильтр «Все подстанции». В PowerShell из `central-service` выполните команды ниже. При другом имени пользователя замените `operator`. Скрипт создаёт две новые учебные подстанции и выводит их имена, ID заявки и UUID событий. Каждый запуск создаёт отдельную серию.

   ```powershell
   $testsDir = (Resolve-Path backend/tests).Path
   docker compose run --rm --no-deps --volume "${testsDir}:/tests:ro" -e PYTHONPATH=/srv/central consumer python /tests/dispatcher_scenario.py operator
   ```

2. Выберите «Северная» с указанной скриптом меткой серии. В «Последних детекциях» должны появиться две строки. Более ранняя содержит номер заявки, более поздняя — номер тревоги. У поздней детекции один UUID для обеих отправок. В ленте должна появиться ровно одна тревога. Откройте её и сравните UUID, время обнаружения и время создания тревоги.
3. Проверьте оборудование «Северной». Камера № 1 и её узел должны иметь статус «В сети», у узла отображается время heartbeat. Переключите фильтр на «Южную» той же серии. Отобразится другая камера № 1, пустые лента и таблица, а у узла — сообщение об отсутствии heartbeat.

## Контракт Kafka для разработчика узла

Узел публикует JSON в UTF-8. Для `camera.status` и `camera.detections` ключ Kafka — отдельная строка `ID подстанции:номер камеры` без пробелов. Для обоих примеров ниже это `10:1`. JSON-имена регистрозависимы. `Sender` — числовой ID зарегистрированной подстанции, `id` — UUID события. При повторной отправке узел сохраняет тот же UUID и содержание.

**`camera.status`**

```json
{"id":"d38b1cf9-c27b-4a03-b662-b40cf9510da9","Camera_id":1,"Time":"2026-11-25T10:00:00+03:00","Viable":false,"Sender":10}
```

`Viable: true` задаёт `online`, `false` — `offline`. Каждое новое событие попадает в `audit_log`. Текущее состояние меняется при первом событии или при `Time` позже сохранённого `cameras.status_at`. При равном времени действует первое принятое состояние. В журнале остаются и запоздалые сообщения.

**`camera.detections`**

```json
{"id":"59639911-f069-4f59-befb-0f17b6290d3c","camera_id":1,"zone_id":101,"detected_time":"2026-11-25T09:59:50+03:00","person_count":1,"confidence":0.99,"is_alert":true,"file":"frames/example.jpg","Sender":10}
```

Оба события адресуют камеру по составному ключу `(substation_id, camera_id)`. `zone_id` — ID зоны из справочника `roi_zones`, принадлежащей этой камере. Если зона не определена, передайте `"zone_id": null`. `Time` и `detected_time` — ISO 8601 с часовым поясом. `person_count` — целое число от 1 до 32767, `confidence` — число от 0 до 1.

Consumer сохраняет UUID, время обнаружения, камеру, зону, количество людей, уверенность модели и исходный путь `file`. Флаг `is_alert=true` означает, что человек пересёк запрещённую зону. Поле обязательно во входном JSON.

| Событие | Результат одной транзакции |
|---|---|
| `is_alert=false` | Детекция и запись журнала. `matched_request_id` остаётся NULL. |
| `is_alert=true`, заявка подходит | Детекция со ссылкой на заявку и запись журнала. |
| `is_alert=true`, подходящих заявок нет | Детекция, запись журнала и одна тревога `new`. Подстанция и узел берутся из камеры, `alerts.created_at` выставляет центральная PostgreSQL. |

Центр ищет активную заявку той же подстанции с `deleted_at IS NULL` по включительному интервалу `valid_from <= detected_time <= valid_to`. При пересечении интервалов приоритет имеет самое позднее начало, при равенстве — меньший ID. Поэтому поздняя доставка обрабатывается по времени съёмки. Для камеры без назначенного узла допустимы первые два исхода. Если требуется тревога, consumer откатывает событие, сохраняет причину в `kafka.rejected` и подтверждает offset после фиксации отказа.

**`node.heartbeat` — предлагаемый контракт.** Ключ Kafka — строка `7`, значение:

```json
{"node_id":7,"Time":"2026-11-25T12:00:00+03:00"}
```

`node_id` — положительное целое и ID существующей строки `edge_nodes`. Сообщению достаточно двух полей. Только строго более новое время (либо первое время) атомарно обновляет `last_heartbeat_at` и переводит узел в `online`. Дубликат и более старое сообщение сохраняют прежний статус, в том числе `offline`. Успешный COMMIT подтверждается и при отсутствии изменений. У каждого узла своя отметка времени. Для heartbeat ошибки контракта и неизвестный ID фиксируются в логах consumer с координатами Kafka. В обычном потоке heartbeat UUID и строки журнала событий не создаются.

В архитектуре указан интервал отправки 10–15 секунд и ориентир потери связи в 2–3 пропущенных интервала. Точный порог в секундах пока открыт. Поэтому даже долго лежавшее в Kafka сообщение с `Time` строго позже последнего известного времени восстанавливает `online`; более раннее или равное время не оживляет отключённый узел.

### Подключение

| Параметр | По умолчанию | Назначение |
|---|---|---|
| `KAFKA_STATUS_TOPIC` | `camera.status` | Топик состояний |
| `KAFKA_DETECTIONS_TOPIC` | `camera.detections` | Топик детекций |
| `KAFKA_HEARTBEAT_TOPIC` | `node.heartbeat` | Предлагаемый топик связи узлов |
| `KAFKA_GROUP_ID` | `central-camera-events` | Группа центра. Её имя сохраняют при перезапуске для продолжения с подтверждённой позиции |
| `KAFKA_BIND_ADDRESS`, `KAFKA_PORT` | `127.0.0.1`, `9092` | Адрес публикации клиентского порта на хосте центра |
| `KAFKA_ADVERTISED_HOST` | `localhost` | Имя или IP, которое брокер сообщает внешнему producer |

Из Docker-сети центра адрес брокера — `kafka:9092`. Локальный producer подключается к `localhost:9092`. Для узла на другой машине с настройками по умолчанию можно пробросить этот порт через SSH с узла: `ssh -N -L 9092:127.0.0.1:9092 user@center`. Producer подключается к `localhost:9092` на стороне туннеля. Для связи через защищённую частную сеть задайте в `.env` IP интерфейса в `KAFKA_BIND_ADDRESS` и достижимое с узла имя в `KAFKA_ADVERTISED_HOST`. Локальный listener использует `PLAINTEXT`; аутентификацию отдельного узла по `Sender` он не выполняет.

Compose поднимает один брокер Apache Kafka в режиме KRaft с томом `kafka_data`. Consumer создаёт недостающие топики (одна партиция, одна реплика) и подписывается на все три. [Образ Apache Kafka](https://kafka.apache.org/41/getting-started/docker/)

### Подтверждение доставки

Для обоих топиков камер consumer фиксирует UUID, детекцию или изменение статуса и связанные записи в одной транзакции PostgreSQL. После COMMIT он синхронно подтверждает offset сообщения. Ошибка записи тревоги или самого COMMIT откатывает транзакцию и оставляет offset для повторной доставки. Старые записи журнала сравниваются в прежнем формате. В новых деталях детекции хранится SHA-256 нормализованного содержимого для проверки конфликта UUID. Точный повтор сохраняет прежнее решение, даже если заявка с тех пор изменилась.

Для событий камер при неверном ключе, неизвестной камере, чужой зоне, некорректном теле или конфликте UUID consumer фиксирует `kafka.rejected` с причиной и координатами сообщения. Подтверждение следует за COMMIT записи отказа.

### Ручная публикация тестовым producer

После `seed-demo` укажите ID подстанции, камеры и узла из выведенных данных. Следующие команды публикуют по одному сообщению каждого вида. Для повтора используйте те же переменные.

```powershell
$station = 1
$camera = 1
$key = '{0}:{1}' -f $station,$camera
$time = [DateTimeOffset]::UtcNow.ToString('o')
$status = @{ id = [guid]::NewGuid().ToString(); Camera_id = $camera; Time = $time; Viable = $true; Sender = $station }
$detection = @{ id = [guid]::NewGuid().ToString(); camera_id = $camera; zone_id = $null; detected_time = $time; person_count = 1; confidence = 0.99; is_alert = $true; file = 'frames/example.jpg'; Sender = $station }
$statusTopic = docker compose exec -T consumer printenv KAFKA_STATUS_TOPIC
$detectionTopic = docker compose exec -T consumer printenv KAFKA_DETECTIONS_TOPIC
# Предлагаемый формат heartbeat. Укажите существующий ID узла из edge_nodes.
$nodeId = 1
$heartbeat = @{ node_id = $nodeId; Time = $time }
$heartbeatTopic = docker compose exec -T consumer printenv KAFKA_HEARTBEAT_TOPIC
"$key|$(ConvertTo-Json -Compress $status)" | docker compose exec -T kafka /opt/kafka/bin/kafka-console-producer.sh --bootstrap-server kafka:9092 --topic $statusTopic --property parse.key=true --property 'key.separator=|'
"$key|$(ConvertTo-Json -Compress $detection)" | docker compose exec -T kafka /opt/kafka/bin/kafka-console-producer.sh --bootstrap-server kafka:9092 --topic $detectionTopic --property parse.key=true --property 'key.separator=|'
"$nodeId|$(ConvertTo-Json -Compress $heartbeat)" | docker compose exec -T kafka /opt/kafka/bin/kafka-console-producer.sh --bootstrap-server kafka:9092 --topic $heartbeatTopic --property parse.key=true --property 'key.separator=|'
```

Проверить результат можно в PostgreSQL. Команда открывает `psql` с настройками контейнера.

```powershell
docker compose exec postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

```sql
SELECT substation_id, camera_id, status, status_at FROM cameras;
SELECT event_uuid, substation_id, camera_id, roi_id, detected_at, matched_request_id, file FROM detections;
SELECT detection_id, substation_id, node_id, status, created_at FROM alerts;
SELECT id, substation_id, last_heartbeat_at, status FROM edge_nodes;
SELECT action, event_uuid, details FROM audit_log ORDER BY id DESC LIMIT 10;
```

## Проверка на отдельной БД и брокере

В отдельной вкладке PowerShell из `central-service` используйте имя тестового проекта и свободные порты. Команды создают независимые тома Kafka и PostgreSQL. Внутри тестовой БД каждый тест создаёт собственную схему. Тестовый producer публикует в отдельные топики, а consumer запускается как отдельный процесс с собственной группой.

```powershell
$env:POSTGRES_DB = 'central_kafka_test'
$env:POSTGRES_HOST_PORT = '25433'
$env:KAFKA_PORT = '29094'
docker compose -p central-kafka-test up -d --build --wait consumer
$tests = (Resolve-Path backend/tests).Path
docker compose -p central-kafka-test run --rm --no-deps -e TEST_POSTGRES=1 -e TEST_KAFKA=1 --volume "${tests}:/tests:ro" consumer python -m unittest discover -s /tests -v
docker compose -p central-kafka-test down -v
```

**Проверено 26 ноября 2026 года.** Все 10 тестов прошли за 26,924 с на отдельной PostgreSQL 16 и реальном брокере Apache Kafka 4.1.2. Проверены три исхода детекции, обе границы срока заявки, отбор по подстанции, статусу и удалению, перекрытия и поздняя доставка. Повторы после изменения заявок и сообщения со старым форматом журнала сохранили первоначальное решение. Ошибка записи тревоги откатила всю транзакцию и оставила offset для повтора. Событие без требуемого назначения узла получило журналируемый отказ.

Для heartbeat проверены два узла одной подстанции, равное и меньшее время после перехода offline, восстановление по более новому времени, неизвестный ID, ошибка ключа и формата времени, параллельные транзакции и подтверждение offset. В этих сценариях таблицы камер, детекций, тревог и журнала сохранили прежние данные.

Перед миграцией основной БД архив `central-before-0006-1795643700866.dump` восстановлен в отдельную БД `restore_pre0006`. Число строк и контрольные суммы содержимого совпали во всех десяти таблицах и в `alembic_version`. Проверка миграции на восстановленной БД прошла. Основная БД затем перешла на `0006_detection_decision`, обе прежние детекции сохранились, `alembic check` не обнаружил расхождений. Группа `central-camera-events` получила партиции всех трёх топиков, HTTP-проверка backend вернула 200.

**Предыдущий прогон, 25 ноября 2026 года (ревизия 0005).** Тогда на PostgreSQL 16 и Kafka 4.1.2 прошли 6 тестов:

- миграция `0004 → 0005` двух камер со сквозными ID `101` и `202`, имеющих локальный номер `1` на разных подстанциях. Обе зоны и обе детекции сохранили правильные ссылки. Откат восстановил связи старого формата;
- совпадение миграций с ORM (`alembic check`), повторный `seed-demo` и чтение камеры по составному ключу;
- приём обоих типов сообщений, сохранение UUID, времени, `file` и обоих значений `is_alert`, изоляция камер `10:1` и `20:1`;
- повторная публикация, повторное чтение тех же offset после перезапуска, поздний статус, чужая зона, неверный ключ и изменение тела при том же UUID;
- ошибка при `COMMIT` PostgreSQL: результат и запись журнала откатились, offset остался неподтверждённым. После восстановления БД тот же offset обработался успешно;
- `GET /api/v1/health` отвечает `200`, прежний `POST /api/v1/node/events` отвечает `404`.

На отдельном стенде команды ручной публикации для камеры `1:1` дали статус `online`, одну детекцию с исходным путём и две записи журнала. Перед обновлением основного центра архив `pg_dump` был восстановлен в тестовую БД и прошёл миграцию. После обновления основного центра сохранились одна камера и две связанные с ней детекции. Главная страница вернула HTTP 200, а группе `central-camera-events` назначены партиции обоих топиков.
