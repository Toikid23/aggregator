# reset_analysis.py

from app import app, db, Job

def reset_all_analyses(qthread=None): # On ajoute qthread=None
    """
    Réinitialise le statut d'analyse de toutes les offres dans la base de données.
    """
    with app.app_context():
        print("🔍 Recherche des offres déjà analysées...")
        
        # On met à jour toutes les offres en une seule requête efficace
        # On ne touche qu'aux offres qui ont besoin d'être réinitialisées
        updated_count = db.session.query(Job).filter(Job.is_analyzed == True).update({
            Job.is_analyzed: False,
            Job.ai_score: None,
            Job.ai_verdict: None,
            Job.ai_analysis_json: None
        }, synchronize_session=False)

        db.session.commit()
        
        if updated_count > 0:
            print(f"✅ Terminé. {updated_count} offres ont été réinitialisées.")
            print("Vous pouvez maintenant lancer 'python run_ai_analysis.py' pour les ré-analyser avec les nouveaux critères.")
        else:
            print("✅ Aucune offre n'avait besoin d'être réinitialisée.")

if __name__ == '__main__':
    reset_all_analyses()