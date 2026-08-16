# FedoraUP
Uno script per aggiornare e manutenere la propria distro di Fedora (NON immutabile)  
Copia e incolla nel terminale il comando sottostante (accertati di essere nella home del tuo account):  
`curl -sSL https://raw.githubusercontent.com/RootGPT-YouTube/FedoraUP/main/install | bash`  
Adesso avrai un comando nuovo nel terminale - `aggiorna` - che quando lo lancerai aggiornerà tutte le app installate con DNF e FLATPAK e farà anche pulizia dei file e dipendenze obsolete.

## Interfaccia
`aggiorna` ha un'interfaccia originale, pensata per essere chiara e gradevole nel terminale:

- **Header a gradiente truecolor** con il titolo del progetto.
- **Pipeline verticale**: ogni operazione è un nodo collegato (`●` completato, `✗` fallito) con uno spinner ad arco rotante e un timer mentre è in corso.
- **Output pulito**: l'output dei comandi è nascosto durante l'esecuzione e mostrato in un riquadro **solo in caso di errore**.
- **Domande interattive**: se un comando fa una domanda nel terminale (es. fwupd o l'import di una chiave GPG), lo script se ne accorge, la mostra in un riquadro dedicato e ti passa la tastiera — la risposta digitata arriva direttamente al comando, poi la pipeline riprende. Vengono riconosciute sia le domande lasciate a metà riga sia quelle stampate con l'a capo, e i comandi girano senza buffering perché nessuna domanda possa restare invisibile.
- **Scheda di resoconto** finale con operazioni riuscite, tempo impiegato, spazio liberato su disco, necessità di riavvio ed esito dell'autoaggiornamento dello script.

## Aggiornamenti che richiedono il riavvio
Sono quelli che le interfacce grafiche (Discover, GNOME Software) mostrano a parte, con l'avviso di riavviare. `aggiorna` li gestisce tutti:

- **Firmware (fwupd)**: BIOS/UEFI, dbx del Secure Boot, firmware di SSD e periferiche. Vengono installati nella pipeline come gli altri passi; il firmware vero e proprio si applica al riavvio successivo. fwupd viene lanciato **senza** risposta automatica: le sue domande arrivano a te.
- **Aggiornamenti offline già in coda**: se Discover ha messo in attesa dei pacchetti da installare al boot, quella coda viene annullata e gli stessi pacchetti vengono installati subito, dal vivo.
- **Salto di versione di Fedora** (es. 44 → 45): è **opzionale** e viene proposto per ultimo, quando tutto il resto è già aggiornato. Se accetti, la nuova release viene scaricata e installata durante un riavvio.

Alla fine lo script dice **perché** serve un riavvio (nuovo kernel, librerie di sistema aggiornate, firmware in attesa) e **propone di riavviare** — la decisione resta tua.

Operazioni eseguite: `dnf upgrade`, `dnf autoremove`, `flatpak update`, `flatpak uninstall --unused`, `fwupdmgr update`, l'hook opzionale `cromup` (se presente), l'autoaggiornamento dello script stesso e, su richiesta, `dnf system-upgrade` per il salto di versione.
