import parselmouth
from parselmouth.praat import call

# Cargar audio
snd = parselmouth.Sound("output.wav")

# Crear manipulación del sonido
manipulation = call(snd, "To Manipulation", 0.01, 75, 600)

# Extraer el tier de pitch
pitch_tier = call(manipulation, "Extract pitch tier")

# Modificar el tono (Aumentar un 10%)
call(pitch_tier, "Multiply frequencies", snd.xmin, snd.xmax, 0.95)

# Reintegrar el pitch tier modificado
call([pitch_tier, manipulation], "Replace pitch tier")

# Obtener el sonido final corregido
manipulated_snd = call(manipulation, "Get resynthesis (overlap-add)")

# Guardar el archivo corregido
manipulated_snd.save("voz_autotune.wav", "WAV")
