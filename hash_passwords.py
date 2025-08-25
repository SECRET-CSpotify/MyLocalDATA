# hash_passwords.py
from streamlit_authenticator.utilities import Hasher

# Lista de contraseñas en texto plano
passwords = [
    "P:NmZq%512U+",   # para admin
    "X9X;5Pidhe~9",   # para Andres Paz
    "c4Q-_£578;[!",   # para Laura Peña
    "8;v^01mMF5",     # para David Gaviria
    "oYI!/E545AdA",   # para Sergio Martinez
    "hV694)OE3wD)"    # para Stefany Espitia
]

# Generar hashes para cada contraseña
hashes = [Hasher.hash(pwd) for pwd in passwords]

# Mostrar en consola
for pwd, h in zip(passwords, hashes):
    print(f"{pwd} → {h}")
