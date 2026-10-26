"""Distance à vol d'oiseau. Ce n'est pas un itinéraire routier."""

from math import asin, cos, radians, sin, sqrt

RAYON_TERRE_KM = 6371.0


def distance_km(latitude_a, longitude_a, latitude_b, longitude_b):
    """Formule de Haversine, en kilomètres."""
    lat_a, lat_b = radians(latitude_a), radians(latitude_b)
    delta_lat = radians(latitude_b - latitude_a)
    delta_lon = radians(longitude_b - longitude_a)
    arc = sin(delta_lat / 2) ** 2 + cos(lat_a) * cos(lat_b) * sin(delta_lon / 2) ** 2
    return 2 * RAYON_TERRE_KM * asin(sqrt(arc))
