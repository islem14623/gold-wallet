# Gold Wallet

## Database migrations

The backend uses SQLAlchemy 2.0 models and Alembic migrations. Set `DATABASE_URL` to
the PostgreSQL connection URL, install the backend requirements, then run:

```sh
cd backend
pip install -r requirements.txt
alembic upgrade head
```

For the Compose database, configure the project environment and use the internal
service URL (`postgresql://<user>:<password>@db:5432/<database>`) from a container
on the Compose network.

## API

Set `JWT_SECRET` to a private signing secret and configure `DATABASE_URL` and
`REDIS_URL` before starting the backend. The API provides registration and login
under `/auth`, a cached fixed fake quote at `/price`, and authenticated `/buy`,
`/sell`, and `/wallet` endpoints. Buy and sell requests require positive `grams`
and an `idempotency_key`.

Run the backend API tests from `backend/` with:

```sh
pytest
```
