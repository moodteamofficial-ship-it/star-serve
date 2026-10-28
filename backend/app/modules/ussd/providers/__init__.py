from app.modules.ussd.enums import UssdProviderKind
from app.modules.ussd.providers.birdview import BirdviewAdapter
from app.modules.ussd.providers.generic import AfricasTalkingAdapter, GenericFormAdapter
from app.modules.ussd.providers.simulator import SimulatorAdapter

_ADAPTERS = {
    UssdProviderKind.SIMULATOR.value: SimulatorAdapter(),
    UssdProviderKind.BIRDVIEW.value: BirdviewAdapter(),
    UssdProviderKind.GENERIC_FORM.value: GenericFormAdapter(),
    UssdProviderKind.AFRICAS_TALKING.value: AfricasTalkingAdapter(),
}


def get_adapter(kind: str):
    return _ADAPTERS.get(kind) or _ADAPTERS[UssdProviderKind.BIRDVIEW.value]
