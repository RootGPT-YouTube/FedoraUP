# FedoraUP
Uno script per aggiornare e manutenere la propria distro di Fedora (NON immutabile)  
Copia e incolla nel terminale il comando sottostante (accertati di essere nella home del tuo account):  
`curl -sSL https://raw.githubusercontent.com/RootGPT-YouTube/FedoraUP/main/install | bash`  
Adesso avrai un comando nuovo nel terminale - `aggiorna` - che quando lo lancerai aggiornerà tutte le app installate con DNF e FLATPAK e farà anche pulizia dei file e dipendenze obsolete.

## ⚠️ Avviso di responsabilità — leggi prima di usarlo

**AGGIORNA** esegue una sequenza di comandi di sistema (`dnf`, `flatpak`, `fwupdmgr`) per aggiornare Fedora, e su richiesta può portare il sistema operativo a una **nuova versione**.

Sono operazioni che modificano il sistema in profondità. Per quanto lo script sia scritto con cura, un imprevisto resta sempre possibile: un aggiornamento interrotto, un pacchetto difettoso o un firmware andato storto possono lasciare il sistema instabile o non avviabile.

AGGIORNA è distribuito **senza alcuna garanzia**, come previsto dalle sezioni 15 e 16 della licenza [GNU GPL v3](LICENSE). **L'autore non risponde di danni, perdita di dati o sistemi resi inutilizzabili** derivanti dall'uso dello script.

**Usando AGGIORNA lo fai a tuo rischio e ti assumi la piena responsabilità delle modifiche apportate al tuo sistema.** Se hai dati importanti, fai un backup prima di procedere.

Lo stesso avviso compare all'avvio del comando, prima ancora che venga chiesta la password, e richiede una conferma esplicita: qualunque risposta diversa da `y`/`s` fa uscire lo script **senza modificare nulla**.

Nota, al momento: il **passaggio a una nuova versione di Fedora** e la gestione degli **aggiornamenti messi in coda per l'installazione al riavvio** sono stati provati soltanto con comandi simulati, non ancora su un caso reale.

## Interfaccia
`aggiorna` ha un'interfaccia originale, pensata per essere chiara e gradevole nel terminale:

- **Header a gradiente truecolor** con il titolo del progetto.
- **Pipeline verticale**: ogni operazione è un nodo collegato (`●` completato, `✗` fallito) con uno spinner ad arco rotante e un timer mentre è in corso.
- **Output pulito**: l'output dei comandi è nascosto durante l'esecuzione e mostrato in un riquadro **solo in caso di errore**.
- **Domande interattive**: se un comando fa una domanda nel terminale (es. l'import di una chiave GPG), lo script se ne accorge, la mostra in un riquadro dedicato e ti passa la tastiera — la risposta digitata arriva direttamente al comando, poi la pipeline riprende. Vengono riconosciute sia le domande lasciate a metà riga sia quelle stampate con l'a capo, e i comandi girano senza buffering perché nessuna domanda possa restare invisibile. Le domande poste dallo script stesso non passano mai da `read -p` (che stampa il prompt solo se lo stdin è un terminale): il testo viene stampato direttamente e la risposta letta dal terminale, così una domanda non può restare muta.
- **Scheda di resoconto** finale con operazioni riuscite, tempo impiegato, spazio liberato su disco, necessità di riavvio ed esito dell'autoaggiornamento dello script.

## Aggiornamenti che richiedono il riavvio
Sono quelli che le interfacce grafiche (Discover, GNOME Software) mostrano a parte, con l'avviso di riavviare. `aggiorna` li gestisce tutti:

- **Firmware (fwupd)** ⚠️: BIOS/UEFI, dbx del Secure Boot, firmware di SSD e periferiche. Vengono installati nella pipeline come gli altri passi; il firmware vero e proprio si applica al riavvio successivo. **Il firmware viene installato senza chiedere conferma e senza mostrare gli avvisi del produttore**: fwupd si considera non interattivo quando il suo output non va su un terminale — come qui, dove l'output alimenta questa interfaccia — e in quel caso disattiva da solo i propri controlli e le proprie domande. Il riavvio resta comunque una scelta tua: fwupd non riavvia niente (`--no-reboot-check`), la proposta arriva una volta sola alla fine dello script.
- **Aggiornamenti offline già in coda** ⚠️ *non ancora testato su un caso reale*: se Discover ha messo in attesa dei pacchetti da installare al boot, quella coda viene annullata e gli stessi pacchetti vengono installati subito, dal vivo.
- **Salto di versione di Fedora** (es. 44 → 45) ⚠️ *non ancora testato su un caso reale*: è **opzionale** e viene proposto per ultimo, quando tutto il resto è già aggiornato. Se accetti, la nuova release viene scaricata e installata durante un riavvio.

Alla fine lo script dice **perché** serve un riavvio (nuovo kernel, librerie di sistema aggiornate, firmware in attesa) e **propone di riavviare** — la decisione resta tua.

### Flatpak che non si aggiornano (delta rotti)

Per risparmiare banda, Flathub distribuisce le differenze fra due versioni (i *delta statici*) invece dei pacchetti interi. Quando un delta è più grande del limite di ostree, l'aggiornamento si ferma a metà con un errore del tipo `Decompressed delta part exceeds configured limit of ... bytes` (è capitato con *Bottles*): non dipende dal tuo sistema né dalla rete, ed è un errore che si ripete identico a ogni tentativo finché Flathub non rigenera quel delta.

`aggiorna` se ne accorge da solo: riconosce l'errore e rilancia subito quel singolo Flatpak con `--no-static-deltas`, cioè scaricando gli oggetti interi. Si consuma un po' più di banda, ma l'app si aggiorna e il passo resta verde. Se anche il secondo tentativo fallisce, l'errore viene mostrato com'è.

Operazioni eseguite: `dnf upgrade`, `dnf autoremove`, `flatpak update`, `flatpak uninstall --unused`, `fwupdmgr update`, l'hook opzionale `cromup` (se presente), l'autoaggiornamento dello script stesso e, su richiesta, `dnf system-upgrade` per il salto di versione.

## Se sembra piantato

L'output dei comandi normalmente viene buttato via a fine passo, quindi di un blocco non resta traccia. Per averla:

```
AGGIORNA_DEBUG=1 aggiorna
```

Tiene un diario in `/tmp/aggiorna-debug-<pid>/`: una riga con l'ora a ogni passo e a ogni domanda (con la risposta data), più l'output completo di ogni comando. Se lo script si ferma, l'ultima riga del diario dice esattamente dove era arrivato e da quanto tempo era lì. Il percorso viene stampato anche a fine esecuzione.
