<img src="https://raw.githubusercontent.com/Adrew-Kirts/ha-capfile/main/assets/logo.png" alt="Capfile" width="110" align="right">

# Capfile pour Home Assistant

**Votre consommation électrique Linky dans Home Assistant — avec jusqu'à 3 ans d'historique dès l'installation.**

[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge&logo=home-assistant&logoColor=white)](https://hacs.xyz)
[![Release](https://img.shields.io/github/v/release/Adrew-Kirts/ha-capfile?style=for-the-badge&color=41BDF5)](https://github.com/Adrew-Kirts/ha-capfile/releases)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1+-41BDF5.svg?style=for-the-badge&logo=home-assistant&logoColor=white)](https://www.home-assistant.io)
[![License](https://img.shields.io/badge/License-MIT-green.svg?style=for-the-badge)](LICENSE)

La plupart des intégrations énergie partent de zéro : le tableau de bord se remplit au fil des mois.
Capfile récupère l'historique déjà stocké par Enedis et l'injecte en statistiques long terme — le
tableau de bord Énergie est **rempli dès la première synchronisation**.

![Tableau de bord Énergie alimenté par Capfile](https://raw.githubusercontent.com/Adrew-Kirts/ha-capfile/main/assets/energy-dashboard.png)

> Le tableau de bord Énergie standard de Home Assistant, configuré automatiquement par l'intégration.
> Ici huit mois d'historique importés, répartis heures creuses / heures pleines, avec les coûts réels.

## Ce que ça fait

| | |
|---|---|
| **Historique complet** | Jusqu'à 3 ans de relevés injectés en statistiques long terme |
| **Par cadran** | HP/HC, base, Tempo… énergie *et* coût, avec les libellés et couleurs de votre contrat |
| **Tableau de bord Énergie** | Configuré automatiquement, rien à brancher à la main |
| **Injection solaire** | Les compteurs producteurs (P4) sont gérés |
| **Coûts réels** | Prix du kWh et abonnement récupérés depuis votre contrat, modifiables |
| **Thème assorti** | Généré avec les couleurs de vos cadrans |

### Entités créées

| Entité | Unité |
|---|---|
| Consommation ce mois | kWh |
| Coût consommation ce mois | € |
| Coût abonnement ce mois | € |
| Coût total ce mois | € |

Plus une statistique long terme par cadran (énergie + coût) et une statistique `Capfile Coût total estimé`.

## Installation

[![Installer via HACS](https://img.shields.io/badge/HACS-Installer%20via%20HACS-41BDF5?style=for-the-badge&logo=home-assistant&logoColor=white)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Adrew-Kirts&repository=ha-capfile&category=integration)

Ou manuellement dans HACS : menu ⋮ → **Dépôts personnalisés** → `https://github.com/Adrew-Kirts/ha-capfile`
→ catégorie **Intégration** → chercher **Capfile** → télécharger → redémarrer Home Assistant.

Puis **Paramètres → Appareils et services → Ajouter une intégration → Capfile**.

**Sans HACS** — copiez `custom_components/capfile/` dans le dossier `custom_components/` de votre
configuration, puis redémarrez Home Assistant.

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
La [documentation Capfile](https://www.capfile.com/capfile/ha/tuto/) détaille la création du compte
et le rattachement de votre compteur.

## Limitations connues

- **Un seul compteur par installation.** Les statistiques sont écrites sous des identifiants qui ne
  contiennent pas le PRM : configurer deux compteurs les ferait écrire dans les mêmes statistiques.
- Le thème généré nécessite `frontend: themes: !include_dir_merge_named themes/` dans `configuration.yaml`.
- La synchronisation tourne une fois par jour ; les données Enedis ont un jour de décalage.
- Service français uniquement (compteurs Linky, données Enedis).

## Support

| Sujet | Où |
|---|---|
| Bug ou souci avec l'intégration | [Issues GitHub](https://github.com/Adrew-Kirts/ha-capfile/issues) |
| Compte Capfile, données, ... | [Forum Capfile](https://www.capfile.com/app/#/forum/home-assistant/integration-home-assistant) |

## Crédits

L'intégration est développée par **[Capfile](https://www.capfile.com)**, qui fournit également l'API.
Ce dépôt la reconditionne pour HACS avec leur accord. Le [tutoriel officiel](https://www.capfile.com/capfile/ha/tuto/)
reste la référence côté compte et API.

Les écarts avec l'archive distribuée par Capfile sont listés dans le [CHANGELOG](CHANGELOG.md).

<details>
<summary><b>English</b></summary>

<br>

**Capfile for Home Assistant** — French Linky electricity consumption, with up to 3 years of history.

Capfile is a French service that retrieves smart-meter (Linky) data from Enedis. Most energy
integrations start from zero and fill up over months; this one imports the history Enedis already
holds as long-term statistics, so the Energy dashboard is populated from the first sync.

**Features** — full history import, per-tariff-period breakdown (peak/off-peak/Tempo) for energy and
cost, automatic Energy dashboard setup, solar injection support for prosumer meters, real contract
pricing, and a generated theme matching your tariff colours.

**Install** — HACS → Custom repositories → `https://github.com/Adrew-Kirts/ha-capfile` → category
Integration. Then add it from Settings. Sign-in is your Capfile login and password; the meter is
picked from a list.

**Note** — French Linky meters only. One meter per installation (see Limitations above).

The integration is developed by [Capfile](https://www.capfile.com); this repository packages it for
HACS with their permission. Integration bugs go to GitHub issues; anything about your Capfile account
belongs on their forum.

</details>
