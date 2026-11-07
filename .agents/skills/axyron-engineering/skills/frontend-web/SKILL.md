---
name: frontend-web
description: Programa interfaces web accesibles, responsive y seguras, manteniendo contratos reales con el backend y evitando funciones simuladas.
---
# Ingeniería frontend web

1. Inspecciona stack, punto de entrada, componentes, estilos, navegación, estado y convenciones actuales.
2. Reutiliza diseño y componentes existentes; no introduzcas un framework o bundler sin necesidad y autorización.
3. Mantén responsive, teclado, foco visible, etiquetas accesibles, contraste y estados de carga/error/vacío.
4. Escapa y trata como no confiables los datos del servidor; evita XSS, HTML inseguro y URLs no validadas.
5. No guardes tokens/secretos en localStorage ni expongas credenciales al navegador.
6. Maneja errores HTTP, sesiones caducadas, reintentos y cancelación de solicitudes.
7. Cada control debe tener comportamiento real; si backend no existe, muestra claramente «Próxima actualización» o deshabilitado.
8. Sin datos demo, mocks productivos ni endpoints imaginarios.
9. Verifica los contratos y permisos backend antes de mostrar acciones.
10. Prueba interacción, navegación, accesibilidad y tamaños de pantalla con herramientas disponibles.
