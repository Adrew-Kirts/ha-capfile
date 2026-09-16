# Changelog

## 0.3.2 — packaging HACS

Première publication sur GitHub. Le code vient de l'archive distribuée par Capfile
(version 0.3.2, `sha256 95cc4c7b6c47bee19bfa75ecac4520eceb45f66574cea53da2f074a293c7eddb`
pour le zip téléchargé sur `https://capfile.com/capfile/ha/latest`), avec les
modifications listées ci-dessous — et rien d'autre. Tous les autres fichiers sont
identiques à l'octet près.

### Distribution

- **Suppression de `update.py`.** Cette entité interrogeait `capfile.com` et installait
  les nouvelles versions par-dessus son propre dossier. HACS gère les mises à jour, les
  deux mécanismes se seraient marché dessus. `PLATFORMS` passe de `["sensor", "update"]`
  à `["sensor"]`.
- **Assets de marque** dans `custom_components/capfile/brand/` (`icon.png` 256×256,
  `icon@2x.png` 512×512). Depuis Home Assistant 2026.3 les intégrations personnalisées
  servent leur icône depuis ce dossier via `/api/brands/integration/{domain}/{image}` ;
  `home-assistant/brands` n'accepte plus de nouveaux composants personnalisés. Sans ce
  dossier, l'intégration s'affiche avec une icône générique. `logo.png` n'est pas fourni :
  Home Assistant utilise `icon.png` en repli.
- Ajout de `hacs.json`, `LICENSE` (MIT, avec l'accord de Capfile), README, CHANGELOG et
  CI (hassfest + action HACS).

### Corrections de validation

- `manifest.json` : retrait de `min_ha_version`, qui n'existe pas dans le schéma des
  manifests Home Assistant et que hassfest rejette. L'équivalent est `homeassistant`
  dans `hacs.json`, renseigné.
- `manifest.json` : ajout de `energy` en `after_dependencies`. `energy_config.py` importe
  `homeassistant.components.energy` sans que la dépendance soit déclarée.
- `manifest.json` : `codeowners`, `documentation` et `issue_tracker` pointent vers ce
  dépôt ; clés réordonnées (`domain`, `name`, puis alphabétique) comme l'exige hassfest.
- Ajout de `CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)`, requis par
  hassfest dès lors qu'`async_setup` est défini. Effet de bord volontaire : une clé
  `capfile:` avec des sous-clés dans `configuration.yaml` déclenche désormais une erreur
  explicite au lieu d'être ignorée en silence. Aucune configuration YAML n'a jamais été
  documentée pour cette intégration.

### Corrections de bugs

- **`theme.py` — écriture non atomique du fichier de thème.** Un rechargement de
  l'entrée déclenche deux tâches indépendantes (déchargement puis configuration) qui
  écrivaient `themes/capfile.yaml` en parallèle, sans verrou. La version courte écrasait
  partiellement la version longue, produisant un YAML invalide. Comme `configuration.yaml`
  inclut le dossier `themes/`, Home Assistant ne parvenait plus à lire sa configuration et
  démarrait en **mode secours**. Corrigé par un `asyncio.Lock` couvrant la collecte et
  l'écriture, et par une écriture dans un fichier temporaire suivie d'un `os.replace`
  atomique. Vérifié par 10 rechargements dont 5 simultanés : fichier valide, couleurs
  conservées, redémarrage propre.
- **`theme.py` — message d'aide incorrect.** En cas d'échec du rechargement des thèmes,
  l'intégration conseillait d'ajouter `homeassistant: themes: ...` dans
  `configuration.yaml`. Les thèmes se déclarent sous `frontend:`, et le schéma de la clé
  `homeassistant:` refuse les clés inconnues : suivre ce conseil faisait démarrer Home
  Assistant en mode secours. Corrigé dans le message et dans la docstring.
- **`statistics.py` — `UnboundLocalError` quand l'API ne renvoie aucune donnée.**
  `_update_sensor_data` était appelé avec `entries` et `prices`, qui ne sont définis que
  dans la branche « données présentes ». La synchronisation entière échouait
  silencieusement (tâche détachée). L'appel est désormais ignoré quand il n'y a pas de
  données, plutôt que d'écrire des zéros par-dessus les valeurs des capteurs.

### Non corrigé, signalé à Capfile

- Les identifiants de statistiques (`capfile:conso_<cadran>`) ne contiennent pas le PRM :
  deux compteurs configurés écriraient dans les mêmes statistiques. Voir « Limitations
  connues » dans le README.
- Le PRM apparaît dans les logs au niveau INFO.
- `fr.json` ne contient pas `options.step.init.data_description.auto_update_prices` ;
  l'utilisateur francophone voit la chaîne anglaise.
- `strings.json` a six clés de retard sur `translations/en.json`.

Aucune autre modification : API, capteurs, calcul des statistiques, configuration du
tableau de bord Énergie et génération des couleurs du thème sont inchangés.
