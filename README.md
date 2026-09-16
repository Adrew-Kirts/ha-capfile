<div align="center">

<img src="https://raw.githubusercontent.com/Adrew-Kirts/ha-capfile/main/assets/logo.png" width="110" alt="Capfile">

# Capfile pour Home Assistant

**Votre consommation électrique Linky dans Home Assistant — avec jusqu'à 3 ans d'historique.**

[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge&logo=home-assistant&logoColor=white)](https://hacs.xyz)
[![Release](https://img.shields.io/github/v/release/Adrew-Kirts/ha-capfile?style=for-the-badge&color=41BDF5)](https://github.com/Adrew-Kirts/ha-capfile/releases)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1+-41BDF5.svg?style=for-the-badge&logo=home-assistant&logoColor=white)](https://www.home-assistant.io)
[![License](https://img.shields.io/badge/License-MIT-green.svg?style=for-the-badge)](LICENSE)

</div>

---

## Ce que ça fait

L'intégration récupère vos données de consommation via l'API [Capfile](https://www.capfile.com) et les injecte
directement dans Home Assistant — y compris **l'historique**, ce qui est la partie intéressante : le tableau de bord
Énergie est rempli dès l'installation, sans attendre des mois d'accumulation.

<div align="center">
<img src="https://raw.githubusercontent.com/Adrew-Kirts/ha-capfile/main/assets/energy-dashboard.png" alt="Tableau de bord Énergie alimenté par Capfile" width="100%">
<sub>Le tableau de bord Énergie de Home Assistant, configuré automatiquement par l'intégration.<br>
Ici huit mois d'historique importés, répartis heures creuses / heures pleines, avec les coûts réels.</sub>
</div>

- **Historique complet** — jusqu'à 3 ans de relevés injectés en statistiques long terme
- **Par cadran** — HP/HC, base, Tempo… énergie *et* coût, avec les libellés et couleurs de votre contrat
- **Tableau de bord Énergie** configuré automatiquement
- **Injection solaire** — les compteurs producteurs (P4) sont gérés
- **Coûts réels** — prix du kWh et abonnement récupérés depuis votre contrat, modifiables à la main
- **Thème assorti** généré avec les couleurs de vos cadrans

### Entités créées

| Entité | Unité |
|---|---|
| Consommation ce mois | kWh |
| Coût consommation ce mois | € |
| Coût abonnement ce mois | € |
| Coût total ce mois | € |

Plus une statistique long terme par cadran (énergie + coût) et une statistique `Capfile Coût total estimé`.

## Installation

### Via HACS

1. HACS → menu ⋮ → **Dépôts personnalisés**
2. URL : `https://github.com/Adrew-Kirts/ha-capfile` — catégorie : **Intégration**
3. Chercher **Capfile**, télécharger
4. Redémarrer Home Assistant
5. **Paramètres → Appareils et services → Ajouter une intégration → Capfile**

### Manuellement

Copier `custom_components/capfile/` dans le dossier `custom_components/` de votre configuration, puis redémarrer.

## Configuration

Tout se passe dans l'interface, en trois étapes :

1. **Connexion** — votre identifiant Capfile (login ou e-mail) et votre mot de passe.
   Le mot de passe n'est pas conservé : seule la clé API obtenue est stockée.
2. **Compteur** — vous choisissez le compteur dans la liste renvoyée par votre compte.
   Rien à saisir à la main.
3. **Tarifs** — prix par cadran et abonnement sont pré-remplis depuis votre contrat et
   restent modifiables. Deux options : mise à jour automatique des tarifs, et
   configuration automatique du tableau de bord Énergie.

Tout reste modifiable ensuite dans les options de l'intégration.

La [documentation Capfile](https://www.capfile.com/capfile/ha/tuto/) détaille la création
du compte et le rattachement de votre compteur.

## Limitations connues

- **Un seul compteur par installation.** L'intégration écrit ses statistiques sous des
  identifiants qui ne contiennent pas le PRM. Configurer deux compteurs ferait écrire les
  deux dans les mêmes statistiques, ce qui corrompt l'historique de manière irréversible.
- Le thème généré nécessite `frontend: themes: !include_dir_merge_named themes/` dans
  `configuration.yaml`.
- La synchronisation tourne une fois par jour ; les données Enedis ont un jour de décalage.

## Support

| Sujet | Où |
|---|---|
| Bug ou souci avec l'intégration | [Issues GitHub](https://github.com/Adrew-Kirts/ha-capfile/issues) |
| Compte Capfile, données, facturation | [Forum Capfile](https://www.capfile.com/app/#/forum/home-assistant/integration-home-assistant) |

## Crédits

L'intégration est développée par **[Capfile](https://www.capfile.com)**, qui fournit également l'API.
Ce dépôt n'existe que pour la rendre installable via HACS, avec leur accord.

Le [tutoriel officiel Capfile](https://www.capfile.com/capfile/ha/tuto/) reste la référence côté compte et API.

---

<details>
<summary><b>English</b></summary>

<br>

**Capfile for Home Assistant** — French Linky electricity consumption data, with up to 3 years of history.

Capfile is a French service that retrieves smart meter (Linky) data from Enedis. This integration pulls that
data into Home Assistant and injects it as long-term statistics, so the Energy dashboard is populated
immediately instead of building up over months.

**Features** — full history import, per-tariff-period breakdown (peak/off-peak/Tempo) for both energy and cost,
automatic Energy dashboard setup, solar injection support for prosumer meters, real contract pricing, and a
generated theme matching your tariff colours.

**Install** — HACS → Custom repositories → `https://github.com/Adrew-Kirts/ha-capfile` → category Integration.
Then add the integration from Settings. You need a Capfile API key and your PRM (14-digit meter number).

**Note** — the service covers French Linky meters only.

The integration is developed by [Capfile](https://www.capfile.com). This repository packages it for HACS with
their permission. Bugs with the integration go to GitHub issues; anything about your Capfile account belongs on
their forum.

</details>

<div align="center">
<sub>Intégration par <a href="https://www.capfile.com">Capfile</a> · packaging HACS par <a href="https://github.com/Adrew-Kirts">Ezra Strikwerda</a> · MIT</sub>
</div>
