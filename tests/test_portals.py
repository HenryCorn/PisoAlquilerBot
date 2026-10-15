from pisorentbot.models import Portal
from pisorentbot.portals import RightmoveAdapter


class Client:
    headers = {}


def test_parses_embedded_rightmove_state():
    html = """
    <html><head><title>Mare Street</title></head><body>
    <script>
    window.jsonModel = {"propertyData": {
      "id": 42, "title": "Mare Street, E8 1AA", "price": "£1,250 pcm",
      "bedrooms": 1, "propertyType": "Flat", "description": "Second floor flat",
      "location": {"latitude": 51.54, "longitude": -0.06},
      "images": [{"url": "https://img.test/living.jpg"}]
    }};
    </script>
    <p>Council tax band B. EPC rating C. Available from 18 April 2027.</p>
    </body></html>
    """
    item = RightmoveAdapter(Client(), []).parse(html, "https://rightmove.test/properties/42")
    assert item.portal is Portal.RIGHTMOVE
    assert item.rent_pcm == 1250
    assert item.bedrooms == 1
    assert item.floor == "Second Floor"
    assert item.postcode == "E8 1AA"
    assert item.available_from.isoformat() == "2027-04-18"
