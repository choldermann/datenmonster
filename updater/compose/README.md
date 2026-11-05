Wird in der CI befüllt (siehe .github/workflows/build-push.yml):

- `docker-compose.yml` – der aktuelle Stand aus dem Repo
- `bekannte_staende.txt` – Fingerabdrücke aller je veröffentlichten Stände

Der Updater ersetzt beim Kunden nur eine Compose-Datei, deren Fingerabdruck hier
steht. Von Hand angepasste Dateien bleiben unberührt; der neue Stand landet dann
als `docker-compose.yml.neu` daneben. Lokal gebaut ist das Verzeichnis leer und
der Abgleich abgeschaltet.
