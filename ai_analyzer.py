# ai_analyzer.py

import json
from openai import OpenAI
import textwrap

# ==============================================================================
#  Étape 1 : CONFIGURATION (C'est ici que tu personnalises !)
# ==============================================================================

# ai_analyzer.py

MON_PROFIL_IDEAL = """
## Résumé du Candidat

Candidat en reconversion professionnelle passionné par la technologie, avec un solide bagage en résolution de problèmes dans des environnements techniques exigeants (maintenance industrielle, gestion d'usine de biogaz). Je suis en transition vers les métiers du Web3 et du Web2, avec une forte motivation pour apprendre et monter en compétences rapidement, notamment en développement. Je recherche un rôle junior (0-3 ans d'expérience) où je peux apporter ma rigueur, mon autonomie et mon esprit d'équipe, tout en développant une expertise technique.

---

## Compétences Transversales (Soft Skills)

- **Résolution de Problèmes :** Très forte capacité à diagnostiquer des pannes complexes et à trouver des solutions sous pression.
- **Autonomie et Rigueur :** Habitué à travailler de manière indépendante et à maintenir des systèmes opérationnels critiques.
- **Apprentissage Rapide :** Forte capacité démontrée à apprendre des domaines complexes (mécanique, biologie, Web3) et des langues (anglais en cours d'amélioration active).
- **Esprit d'Équipe :** Expérience en gestion d'équipe et forte orientation vers le service client/utilisateur.
- **Persévérance (Grit) :** Détermination à résoudre les problèmes jusqu'au bout, avec l'humilité d'apprendre de ses erreurs.
- **Communication :** En cours d'amélioration active de l'anglais pour m'intégrer dans des équipes internationales.

---

## Compétences Techniques et Connaissances Actuelles

- **Domaine de prédilection :** Web3. Connaissance approfondie de l'écosystème, des protocoles, des DApps et des dynamiques de marché du point de vue de l'utilisateur et de l'observateur.
- **Domaines ouverts :** Également très intéressé par les opportunités dans le Web2, notamment dans des rôles liés à l'opérationnel, au support ou à la qualité.
- **Développement :** Niveau débutant. Je suis conscient que c'est une compétence à développer et je suis extrêmement motivé pour apprendre sur le tas (Python, JavaScript, etc.). Je ne suis PAS un développeur expérimenté.
- **Outils :** Utilisation et interaction avec de nombreuses applications décentralisées (DeFi, NFTs, etc.).
- **Langues :** Français (natif), Anglais (niveau intermédiaire en amélioration quotidienne).

---

## Ce que je recherche (Rôle Idéal)

- **Niveau de séniorité :** Junior, Débutant, ou poste nécessitant moins de 3 ans d'expérience.
- **Types de rôles ciblés :**
    - **Support Technique / Customer Support :** Aider les utilisateurs, résoudre leurs problèmes.
    - **Assurance Qualité (QA) :** Tester les applications, remonter les bugs, assurer la qualité du produit.
    - **Opérations (Ops) / BizOps :** Aider à la bonne marche des opérations de l'entreprise.
    - **Community Management (technique) :** Animer une communauté (Discord, etc.) en répondant aux questions techniques de base.
    - **Tout rôle "passerelle"** qui me permet de contribuer avec mes compétences actuelles tout en me formant techniquement.

---

## Ce que j'évite

- **Rôles de développeur Senior ou Confirmé :** Mon niveau technique actuel n'est pas suffisant. Je cible des postes où je peux apprendre le développement.
- **Rôles purement commerciaux / vente pure :** Je suis plus intéressé par le produit et la technique.
- **Environnements non-techniques :** Je veux rester dans un cadre technologique.
"""

# ai_analyzer.py

MES_CRITERES_STRICTS = """
## Points Stricts et Incontournables (non-négociables)

- **Contrat :** CDI (Contrat à Durée Indéterminée) exclusivement. Tout autre type de contrat (CDD, freelance, stage, alternance) est un motif de rejet.

- **Télétravail :** 100% Télétravail (Full remote) est OBLIGATOIRE. Les offres en mode hybride, sur site, ou qui ne mentionnent pas explicitement le télétravail complet doivent être notées négativement.

- **Localisation :** Le poste doit être ouvert aux résidents en France, même s'il est en télétravail. Une préférence pour les entreprises basées en France, mais ouvert à l'international si le poste est accessible depuis la France.

- **Niveau d'Expérience Requis :** L'offre doit demander 0, 1, 2 ou 3 ans d'expérience maximum. Les postes "Junior" ou "Débutant" sont parfaits. Les postes "Senior", "Confirmé", "Lead", ou demandant plus de 3 ans d'expérience sont à rejeter.

## "Red Flags" Absolus (Motifs de Rejet)

- **Type d'entreprise à ÉVITER à TOUT PRIX :**
  - **ESN (Entreprise de Services du Numérique)**
  - **SSII** (ancien nom pour ESN)
  - **Société de conseil / Consulting firm**
  - **Agence de recrutement / Cabinet de recrutement**
  - Tout intermédiaire qui place des "consultants" chez des clients.
  - Mots-clés à surveiller qui signalent une ESN : "mission chez notre client", "rejoindre notre pôle de consultants", "intervenir sur des projets clients". Si ces termes apparaissent, l'offre doit être rejetée.

- **Type d'entreprise RECHERCHÉ :**
  - Client final (l'entreprise qui développe son propre produit).
  - Startup (surtout dans la tech, Web3, Web2).
  - PME (produit tech ou SaaS).
  - Éditeur de logiciel.
"""

# --- B. LE CERVEAU DE L'IA ---
client = OpenAI(
    base_url='http://localhost:11434/v1',
    api_key='ollama', # la clé api n'est pas importante pour ollama, mais il en faut une
)

PROMPT_TEMPLATE = """
Tu es un recruteur technique expert et un assistant personnel de recherche d'emploi.
Ta mission est d'analyser une offre d'emploi par rapport au profil et aux critères de ton client.
Ta réponse doit être UNIQUEMENT le code JSON demandé, sans aucun autre texte, commentaire, ou explication.

## Mon Profil :
{profil}

## Mes Critères Stricts (Points non-négociables) :
{criteres}

## L'Offre d'Emploi à Analyser :
{offre}

## Ton Analyse (au format JSON) :
Produis une analyse JSON structurée comme suit. Le score doit refléter la correspondance globale (compétences ET critères).
{{
  "titre_poste": "Le titre exact de l'offre",
  "nom_entreprise": "Le nom de l'entreprise si trouvé",
  "score_pertinence": "Un score entier sur 100",
  "verdict_court": "Une phrase de conclusion (ex: 'Excellent match', 'À éviter', 'Match partiel').",
  "analyse_criteres": {{
    "respectes": true ou false,
    "details": "Explique pourquoi les critères sont respectés ou non (ex: 'CDI mentionné', 'L'entreprise semble être une ESN', 'Rôle de Backend pur respecté')."
  }},
  "analyse_competences": {{
    "competences_correspondantes": ["Liste des compétences que je possède et qui sont demandées."],
    "competences_manquantes": ["Liste des compétences demandées que je ne possède pas."]
  }},
  "points_positifs": ["Liste d'autres points positifs (ex: 'Secteur d'activité intéressant', 'Télétravail généreux')."],
  "points_negatifs_red_flags": ["Liste des signaux d'alerte (ex: 'Description vague', 'Le mot \\"consultant\\" suggère une ESN')."]
}}
"""

def analyze_job_offer(job):
    """
    Analyse une offre d'emploi (objet Job de la DB) avec l'IA.
    Retourne un dictionnaire avec l'analyse, ou None si une erreur survient.
    """
    print(f"🤖 Lancement de l'analyse IA pour l'offre ID: {job.id} - '{job.title}'")

    # 1. On construit le texte complet de l'offre pour l'IA
    offre_texte = textwrap.dedent(f"""
        Titre: {job.title}
        Entreprise: {job.company}
        Lieu: {job.location}
        Tags/Contrat: {job.tags or 'Non spécifié'}
        Salaire: {job.salary or 'Non spécifié'}
        ---
        Description:
        {job.description or 'Pas de description détaillée.'}
    """).strip()

    # 2. On prépare le prompt final
    prompt_final = PROMPT_TEMPLATE.format(
        profil=MON_PROFIL_IDEAL,
        criteres=MES_CRITERES_STRICTS,
        offre=offre_texte
    )

    try:
        # 3. On envoie la requête à Ollama
        response = client.chat.completions.create(
            model="llama3:8b",
            messages=[{"role": "user", "content": prompt_final}],
            response_format={"type": "json_object"},
            temperature=0.1
        )

        # 4. On retourne le résultat JSON parsé
        analyse_json = json.loads(response.choices[0].message.content)
        print(f"✅ Analyse IA réussie pour l'offre ID: {job.id}. Verdict : {analyse_json.get('verdict_court')}")
        return analyse_json

    except Exception as e:
        print(f"❌ ERREUR lors de l'analyse IA de l'offre ID {job.id}: {e}")
        return None