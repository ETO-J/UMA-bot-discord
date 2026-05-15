import nonebot
from nonebot.adapters.discord import Adapter as DISCORDAdapter


nonebot.init()

driver = nonebot.get_driver()
driver.register_adapter(DISCORDAdapter)

nonebot.load_from_toml("pyproject.toml")

if __name__ == "__main__":
    nonebot.run()
