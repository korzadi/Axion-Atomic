# QLoRA externo

No entrenar en el VPS de 16 GB. En una máquina GPU externa:
1. Curar ejemplos con licencia y procedencia conocidas; retirar secretos y datos personales.
2. Separar train/validation/test por repositorio o fuente para evitar fuga.
3. Instalar `requirements-gpu.txt` en entorno CUDA compatible.
4. Ejecutar `train_qlora.py` y vigilar VRAM.
5. Comparar base vs adaptador en conjunto de evaluación reservado.
6. Publicar solo si mejora y no empeora seguridad/calidad.
7. Convertir/combinar y cuantizar siguiendo versiones compatibles con Ollama.

El starter no contiene corpus de entrenamiento real.
