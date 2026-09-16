if __name__ != "__main__":
    import pytest
    pytest.skip("Legacy manual database script; excluded from automated tests.", allow_module_level=True)

from app.services.search_service import SearchService


print("HOSTNAME SEARCH")
print("-" * 40)

results = SearchService.search_hostname(
    "DUPHOST01"
)

for item in results:
    print(item.hostname)


print()
print("IP SEARCH")
print("-" * 40)

results = SearchService.search_ip(
    "10.80.1.1"
)

for item in results:
    print(item.hostname)
