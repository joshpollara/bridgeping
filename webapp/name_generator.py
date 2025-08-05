import random
import string

# Docker-style name generation
# Adjectives + famous scientists/inventors

ADJECTIVES = [
    "admiring", "adoring", "affectionate", "agitated", "amazing", "angry",
    "awesome", "blissful", "bold", "boring", "brave", "brilliant", "busy",
    "charming", "clever", "cool", "compassionate", "competent", "confident",
    "cranky", "crazy", "dazzling", "determined", "distracted", "dreamy",
    "eager", "ecstatic", "elastic", "elated", "elegant", "eloquent",
    "epic", "fervent", "festive", "flamboyant", "focused", "friendly",
    "frosty", "gallant", "gifted", "goofy", "gracious", "happy", "hardcore",
    "heuristic", "hopeful", "hungry", "infallible", "inspiring", "jolly",
    "jovial", "keen", "kind", "laughing", "loving", "lucid", "magical",
    "mystifying", "modest", "musing", "naughty", "nervous", "nifty",
    "nostalgic", "objective", "optimistic", "peaceful", "pedantic", "pensive",
    "practical", "priceless", "quirky", "quizzical", "recursing", "relaxed",
    "reverent", "romantic", "sad", "serene", "sharp", "silly", "sleepy",
    "stoic", "stupefied", "suspicious", "sweet", "tender", "thirsty",
    "trusting", "unruffled", "upbeat", "vibrant", "vigilant", "vigorous",
    "wizardly", "wonderful", "xenodochial", "youthful", "zealous", "zen"
]

NAMES = [
    "agnesi", "albattani", "allen", "almeida", "antonelli", "archimedes",
    "ardinghelli", "aryabhata", "austin", "babbage", "banach", "banzai",
    "bardeen", "bartik", "bassi", "beaver", "bell", "benz", "berlekamp",
    "berners-lee", "bhabha", "bhaskara", "black", "blackburn", "blackwell",
    "bohr", "booth", "borg", "bose", "bouman", "boyd", "brahmagupta",
    "brattain", "brown", "buck", "burnell", "cannon", "carson", "cartwright",
    "carver", "cerf", "chandrasekhar", "chaplygin", "chatelet", "chatterjee",
    "chebyshev", "cohen", "chaum", "clarke", "colden", "cori", "cray",
    "curie", "darwin", "davinci", "dewdney", "dhawan", "diffie", "dijkstra",
    "dirac", "driscoll", "dubinsky", "easley", "edison", "einstein", "elbakyan",
    "elgamal", "elion", "ellis", "engelbart", "euclid", "euler", "faraday",
    "feistel", "fermat", "fermi", "feynman", "franklin", "gagarin", "galileo",
    "galois", "ganguly", "gates", "gauss", "germain", "goldberg", "goldstine",
    "goldwasser", "golick", "goodall", "gould", "greider", "grothendieck",
    "haibt", "hamilton", "haslett", "hawking", "hellman", "heisenberg",
    "hermann", "herschel", "hertz", "heyrovsky", "hodgkin", "hofstadter",
    "hoover", "hopper", "hugle", "hypatia", "ishizaka", "jackson", "jang",
    "jemison", "jennings", "jepsen", "johnson", "joliot", "jones", "kalam",
    "kapitsa", "kare", "keldysh", "keller", "kepler", "khayyam", "kilby",
    "kirch", "knuth", "kowalevski", "lalande", "lamarr", "lamport", "leakey",
    "leavitt", "lederberg", "lehmann", "lewin", "lichterman", "liskov",
    "lovelace", "lumiere", "mahavira", "margulis", "matsumoto", "maxwell",
    "mayer", "mccarthy", "mcclintock", "mclaren", "mclean", "mcnulty",
    "mendel", "mendeleev", "meitner", "meninsky", "merkle", "mestorf",
    "mirzakhani", "montalcini", "moore", "morse", "murdock", "moser",
    "napier", "nash", "neumann", "newton", "nightingale", "nobel", "noether",
    "northcutt", "noyce", "panini", "pare", "pascal", "pasteur", "payne",
    "perlman", "pike", "poincare", "poitras", "proskuriakova", "ptolemy",
    "raman", "ramanujan", "ride", "ritchie", "rhodes", "robinson", "roentgen",
    "rosalind", "rubin", "saha", "sammet", "sanderson", "satoshi", "shamir",
    "shannon", "shaw", "shirley", "shockley", "shtern", "sinoussi", "snyder",
    "solomon", "spence", "stonebraker", "sutherland", "swanson", "swartz",
    "swirles", "taussig", "tereshkova", "tesla", "tharp", "thompson",
    "torvalds", "tu", "turing", "varahamihira", "vaughan", "visvesvaraya",
    "volhard", "villani", "wescoff", "wilbur", "wiles", "williams", "williamson",
    "wilson", "wing", "wozniak", "wright", "wu", "yalow", "yonath", "zhukovsky"
]


def generate_watchlist_name():
    """Generate a Docker-style name (adjective-name)"""
    adjective = random.choice(ADJECTIVES)
    name = random.choice(NAMES)
    return f"{adjective}-{name}"


def generate_unique_watchlist_name(check_exists_func):
    """Generate a unique watchlist name, checking against existing names"""
    max_attempts = 100
    for _ in range(max_attempts):
        name = generate_watchlist_name()
        if not check_exists_func(name):
            return name
    
    # If we couldn't find a unique name from the word lists, 
    # append random characters
    base_name = generate_watchlist_name()
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
    return f"{base_name}-{suffix}"


def is_valid_watchlist_name(name):
    """Check if a watchlist name is valid (adjective-name format)"""
    if not name or not isinstance(name, str):
        return False
    
    parts = name.split('-')
    if len(parts) < 2:
        return False
    
    # Allow names with suffixes (e.g., clever-einstein-abc123)
    # but require at least adjective-name format
    return True