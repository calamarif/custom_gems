from .factory import Factory
from .generator import Generator
from .proxy import Faker

VERSION = "25.9.1"

__all__ = ("Factory", "Generator", "Faker")

# from datetime import datetime
# fake = Faker('en_US')
# print(fake.uuid4())
# # print(fake.date_between(start_date=datetime.strptime('2024-01-01', "%Y-%m-%d").date(), end_date=datetime.strptime('2024-01-31', "%Y-%m-%d").date()))
# # print(fake.date_time_between(start_date=datetime.strptime('2024-01-01 10:02:38', "%Y-%m-%d %H:%M:%S").date(), end_date=datetime.strptime('2024-01-31 11:05:33', "%Y-%m-%d %H:%M:%S").date()))
