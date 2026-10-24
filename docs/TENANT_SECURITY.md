# Cloisonnement AgriTogo — 24 octobre 2026

Les pages publiques ne lisent plus le journal global ai_conversations. Les historiques
web sont isolés par identifiant de session aléatoire signé, limités à 20 messages et
100 sessions par processus, et expirent après 30 minutes. Ils sont éphémères : un
redémarrage ou un changement de worker peut perdre cet historique, jamais le remplacer
par celui d'un autre utilisateur. La façade Next.js conserve sa persistance autorisée.
Un numéro de carte envoyé à agent/chat ne permet plus d'écrire le journal d'un tiers.
Chaque appel d'agent construit une mémoire neuve. Les outils Kobo, données globales,
risque et écritures sont exclus des agents publics ; seule une garde super_admin
vérifiée peut donner la capacité privée, retirée à la fin de la requête. Les routes
d'analyse globale et de mémoire exigent aussi cette garde en accès direct.

Le modèle de risque est signalé expérimental et non validé pour une décision de crédit.
L'ancien rendement synthétique /ml/crop-yield répond 410 ; utiliser l'estimation FAO-33,
qui reste explicitement non validée localement. Aucun SMS ni paiement n'est ajouté.

Validation locale sans prestataire : python -m pytest -q tests/test_tenant_security.py.
Les tests exercent les vrais handlers Flask, les fuites croisées entre visiteurs,
la suppression limitée à sa session, la garde API directe, le rejet de carte fournie
par un tiers, les limites mémoire et les agents neufs avec outils publics seulement.
