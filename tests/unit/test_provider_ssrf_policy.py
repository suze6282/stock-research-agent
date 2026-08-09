import pytest

from stock_research_agent.providers.http_policy import ProviderAddressPolicy


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "172.16.0.1",
        "192.168.0.1",
        "169.254.169.254",
        "0.0.0.0",
        "224.0.0.1",
        "192.0.2.1",
        "198.51.100.1",
        "203.0.113.1",
        "::1",
        "fe80::1",
        "fc00::1",
        "ff02::1",
        "::",
        "2001:db8::1",
        "::ffff:8.8.8.8",
    ],
)
def test_address_policy_rejects_non_global_and_ipv4_mapped_addresses(
    address: str,
) -> None:
    with pytest.raises(ValueError, match="PROVIDER_ADDRESS_FORBIDDEN"):
        ProviderAddressPolicy().validate("data.example.com", (address,))


def test_address_policy_accepts_one_stable_public_resolution_set() -> None:
    policy = ProviderAddressPolicy()
    first = policy.validate("data.example.com", ("8.8.8.8", "2606:4700:4700::1111"))
    second = policy.validate(
        "data.example.com",
        ("2606:4700:4700::1111", "8.8.8.8"),
    )

    assert first == second == ("8.8.8.8", "2606:4700:4700::1111")


def test_address_policy_rejects_mixed_safe_unsafe_and_dns_rebinding() -> None:
    policy = ProviderAddressPolicy()
    with pytest.raises(ValueError, match="PROVIDER_ADDRESS_FORBIDDEN"):
        policy.validate("mixed.example.com", ("8.8.8.8", "127.0.0.1"))

    policy.validate("data.example.com", ("8.8.8.8",))
    with pytest.raises(ValueError, match="PROVIDER_DNS_REBINDING"):
        policy.validate("data.example.com", ("1.1.1.1",))


def test_address_policy_rejects_empty_invalid_and_ambiguous_host() -> None:
    policy = ProviderAddressPolicy()
    for host, addresses in (
        ("", ("8.8.8.8",)),
        ("*.example.com", ("8.8.8.8",)),
        ("data.example.com", ()),
        ("data.example.com", ("not-an-ip",)),
    ):
        with pytest.raises(ValueError):
            policy.validate(host, addresses)
