#!/bin/sh
#genera la respuesta de salud con el id de la tarea y la zona (metadata de ecs)
tarea=$(hostname)
zona="local"
if [ -n "$ECS_CONTAINER_METADATA_URI_V4" ]; then
  datos=$(wget -qO- -T 2 "$ECS_CONTAINER_METADATA_URI_V4/task" 2>/dev/null)
  t=$(echo "$datos" | sed -n 's/.*"TaskARN": *"[^"]*\/\([^"]*\)".*/\1/p')
  z=$(echo "$datos" | sed -n 's/.*"AvailabilityZone": *"\([^"]*\)".*/\1/p')
  [ -n "$t" ] && tarea="$t"
  [ -n "$z" ] && zona="$z"
fi
printf '{"estado":"ok","tareaId":"%s","zona":"%s"}' "$tarea" "$zona" > /usr/share/nginx/html/salud-web.json
