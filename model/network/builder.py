from utils.core import Registry

Networks = Registry("network")


def build_network(network_name, **kwargs):
    try:
        network = Networks.get(network_name)
        return network(**kwargs)
    except Exception as error:
        print(f"network build fail: {error}")
        return None
