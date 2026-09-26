from alembic import context

from backend.app.config import Settings
from backend.app.database import Base, make_engine
from backend.app.identity import models  # noqa: F401
from backend.app.inventory import models as inventory_models  # noqa: F401
from backend.app.purchases import models as purchase_models  # noqa: F401

target_metadata = Base.metadata
database_url = context.config.attributes.get("database_url") or Settings().database_url

if context.is_offline_mode():
    context.configure(
        url=database_url, target_metadata=target_metadata, literal_binds=True, compare_type=True
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = make_engine(database_url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
