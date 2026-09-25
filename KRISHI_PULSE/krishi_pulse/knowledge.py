"""Agronomy knowledge base: soils and crops.

Values are typical textbook / FAO-56 style figures meant as sensible defaults.
Tune them with your local Krishi Vigyan Kendra (KVK) or agri-university data.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Soil:
    key: str
    name: str
    field_capacity: float   # volumetric %, all the water soil holds after drainage
    wilting_point: float    # volumetric %, plants cannot extract water below this


SOILS = {
    "sandy":      Soil("sandy", "Sandy soil", 18.0, 8.0),
    "red_loam":   Soil("red_loam", "Red loam", 28.0, 14.0),
    "black_clay": Soil("black_clay", "Black clay (regur)", 40.0, 24.0),
    "silt_loam":  Soil("silt_loam", "Silt loam", 32.0, 15.0),
}


@dataclass(frozen=True)
class Stage:
    name: str
    days: int              # length of the stage in days
    kc: float              # crop coefficient (water use relative to reference ET)
    root_cm: int           # effective root depth
    mad: float             # allowed depletion of available water before irrigating


@dataclass(frozen=True)
class Disease:
    name: str
    min_humidity: float
    tmin: float
    tmax: float


@dataclass(frozen=True)
class Crop:
    key: str
    name: str
    stages: tuple
    ph_min: float
    ph_max: float
    ec_max: float          # dS/m salinity tolerance
    heat_c: float          # daytime max above which the crop is stressed
    cold_c: float          # night minimum below which the crop is stressed
    n_low_mg_kg: float     # sensor nitrogen considered low
    disease: Disease


@dataclass(frozen=True)
class Pest:
    key: str
    name: str
    crops: tuple
    symptoms: tuple
    action: str
    urgency: str


CROPS = {
    "tomato": Crop("tomato", "Tomato",
        (Stage("Establishment", 25, 0.60, 30, 0.40), Stage("Vegetative", 40, 0.90, 50, 0.40),
         Stage("Flowering & fruiting", 45, 1.15, 70, 0.40), Stage("Ripening", 30, 0.80, 70, 0.50)),
        6.0, 7.0, 2.5, 35, 10, 40, Disease("late blight / early blight", 85, 12, 26)),
    "chilli": Crop("chilli", "Chilli",
        (Stage("Establishment", 30, 0.60, 30, 0.30), Stage("Vegetative", 35, 0.90, 40, 0.30),
         Stage("Flowering & fruiting", 50, 1.05, 60, 0.30), Stage("Ripening", 30, 0.85, 60, 0.40)),
        6.0, 7.0, 1.5, 36, 12, 35, Disease("anthracnose / fruit rot", 85, 20, 32)),
    "maize": Crop("maize", "Maize",
        (Stage("Establishment", 20, 0.30, 30, 0.55), Stage("Vegetative", 35, 0.70, 60, 0.55),
         Stage("Tasselling & silking", 40, 1.20, 90, 0.50), Stage("Grain filling", 30, 0.60, 100, 0.60)),
        5.8, 7.5, 1.7, 38, 8, 30, Disease("leaf blight", 80, 18, 27)),
    "ragi": Crop("ragi", "Ragi (finger millet)",
        (Stage("Establishment", 20, 0.30, 25, 0.55), Stage("Tillering", 35, 0.80, 40, 0.55),
         Stage("Flowering & grain", 40, 1.00, 50, 0.50), Stage("Maturity", 25, 0.40, 50, 0.65)),
        5.0, 8.0, 3.0, 38, 8, 25, Disease("blast", 90, 20, 28)),
    "groundnut": Crop("groundnut", "Groundnut",
        (Stage("Establishment", 25, 0.40, 25, 0.50), Stage("Vegetative", 30, 0.75, 40, 0.50),
         Stage("Pegging & pod set", 45, 1.15, 50, 0.40), Stage("Maturity", 30, 0.60, 50, 0.60)),
        5.8, 7.0, 3.2, 36, 12, 25, Disease("leaf spot / rust", 80, 20, 30)),
}

PESTS = {
    "aphids": Pest("aphids", "Aphids", ("tomato", "chilli", "maize"),
        ("clusters_under_leaves", "sticky_leaves", "leaf_curl", "ants_on_plant"),
        "Check growing tips and leaf undersides; use a strong water spray first and protect beneficial insects.", "Monitor within 24 hours"),
    "whitefly": Pest("whitefly", "Whitefly", ("tomato", "chilli"),
        ("small_white_fliers", "sticky_leaves", "yellowing_leaves", "leaf_curl"),
        "Inspect leaf undersides and use yellow sticky traps; follow local KVK guidance if numbers keep rising.", "Act this week"),
    "fruit_borer": Pest("fruit_borer", "Fruit borer", ("tomato", "chilli"),
        ("holes_in_fruit", "frass_at_hole", "wilting_shoots", "caterpillar_seen"),
        "Remove damaged fruit and scout at dusk for larvae; use only a locally approved treatment and dose.", "Scout tonight"),
    "thrips": Pest("thrips", "Thrips", ("chilli",),
        ("silvery_streaks", "curled_leaves", "flower_drop", "tiny_insects"),
        "Check flowers with a white paper tap test and remove badly damaged growth; avoid broad-spectrum sprays during bloom.", "Scout within 48 hours"),
    "spider_mites": Pest("spider_mites", "Spider mites", ("tomato", "chilli"),
        ("fine_webbing", "bronze_leaves", "speckled_leaves", "dry_leaf_edges"),
        "Check leaf undersides with a hand lens, reduce dust and heat stress, and ask a local officer about a selective miticide.", "Act this week"),
    "fall_armyworm": Pest("fall_armyworm", "Fall armyworm", ("maize",),
        ("windowpanes_on_leaves", "frass_in_whorl", "caterpillar_seen", "ragged_leaves"),
        "Open the whorl and look for larvae or fresh frass; hand-pick early infestations and follow local treatment guidance.", "Act within 24 hours"),
    "stem_borer": Pest("stem_borer", "Stem borer", ("maize", "ragi"),
        ("dead_heart", "shot_holes", "frass_in_stem", "stunted_center_shoot"),
        "Pull and destroy badly affected plants, inspect the central whorl, and ask the local extension officer for an approved plan.", "Act within 48 hours"),
    "shoot_fly": Pest("shoot_fly", "Shoot fly", ("ragi",),
        ("dead_heart", "central_shoot_dries", "small_white_maggot", "stunted_center_shoot"),
        "Check young plants at the base of the central shoot and remove dead hearts; use locally recommended seed or field protection.", "Act within 48 hours"),
    "leaf_miner": Pest("leaf_miner", "Leaf miner", ("groundnut",),
        ("serpentine_mines", "blotch_mines", "premature_leaf_drop", "tiny_flies"),
        "Remove heavily mined leaflets, scout new growth, and preserve parasitoids before considering a selective treatment.", "Monitor within 48 hours"),
    "white_grub": Pest("white_grub", "White grub", ("groundnut",),
        ("wilting_in_patches", "roots_eaten", "plants_pull_easily", "white_grub_seen"),
        "Check roots at the edge of affected patches and confirm the grub before treatment; improve field sanitation and follow local advice.", "Confirm this week"),
}


def pests_for(crop_key: str) -> list[Pest]:
    return [pest for pest in PESTS.values() if crop_key in pest.crops]


PEST_HARMS = {
    "aphids": "Sap loss causes curled, weak leaves; honeydew can encourage sooty mould and reduce photosynthesis.",
    "whitefly": "Feeding yellows leaves and can spread viral disease between plants.",
    "fruit_borer": "Larvae tunnel into fruit and shoots, causing rot, fruit drop, and direct yield loss.",
    "thrips": "Scraping damage scars leaves and flowers, causing distortion, flower drop, and possible virus spread.",
    "spider_mites": "Sap feeding creates speckled bronze leaves, early leaf drop, and severe loss of plant vigour.",
    "fall_armyworm": "Larvae shred the whorl and leaves; severe attack can remove the growing tissue and reduce grain formation.",
    "stem_borer": "Boring blocks the stem, causing dead hearts, weak plants, and poor grain or panicle development.",
    "shoot_fly": "Larvae kill the central shoot in young plants, creating dead hearts and missing plant stands.",
    "leaf_miner": "Leaf tunnels reduce green leaf area and photosynthesis; severe damage causes premature leaf drop.",
    "white_grub": "Root feeding cuts water and nutrient uptake, causing patchy wilting, lodging, and plant death.",
}


def pest_harm(pest_key: str) -> str:
    return PEST_HARMS.get(pest_key, "Can reduce plant vigour and yield; confirm locally before treatment.")
