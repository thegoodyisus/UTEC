#dinero: texto con 2 decimales en la api, centimos enteros por dentro (nunca coma flotante)


def a_centimos(texto):
    entero, decimales = texto.split(".")
    return int(entero) * 100 + int(decimales)


def a_texto(centimos):
    centimos = int(centimos)
    return "%d.%02d" % (centimos // 100, centimos % 100)
