# Correction du démarrage de Kibana

## Symptôme

Kibana redémarrait avant que son endpoint `/api/status` soit disponible. Les journaux Node.js se terminaient par :

```text
FATAL ERROR: Ineffective mark-compacts near heap limit
Allocation failed - JavaScript heap out of memory
```

## Cause

Le heap V8 était limité à 512 Mo (`--max-old-space-size=512`). Cette valeur était insuffisante pendant l'initialisation de Kibana et les migrations des objets enregistrés.

## Correction

- heap Node.js Kibana : 1 024 Mo ;
- limite mémoire du conteneur Kibana : 1 536 Mo ;
- surveillance des journaux pendant l'attente HTTP afin de signaler immédiatement une nouvelle saturation du heap.

Le réglage laisse environ 512 Mo hors heap pour le runtime Node.js, les buffers natifs et les autres allocations du processus.
