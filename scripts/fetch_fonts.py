"""Fetch unmodified OFL fonts and their licenses from a pinned Google Fonts revision."""
from pathlib import Path
import urllib.request
import concurrent.futures
import json
import hashlib

REV='334b789e33413f3aba4264d9aa6c97f7b94c5a2f'
FONTS=[('abel','Abel-Regular'),('abrilfatface','AbrilFatface-Regular'),
('acme','Acme-Regular'),('alata','Alata-Regular'),('aldrich','Aldrich-Regular'),
('amaticsc','AmaticSC-Regular'),('anton','Anton-Regular'),('archivoblack','ArchivoBlack-Regular'),
('arvo','Arvo-Regular'),('bangers','Bangers-Regular'),('barlow','Barlow-Regular'),
('barlowcondensed','BarlowCondensed-Regular'),('bebasneue','BebasNeue-Regular'),
('cabinsketch','CabinSketch-Regular'),('candal','Candal'),('cantarell','Cantarell-Regular'),
('cardo','Cardo-Regular'),('cinzeldecorative','CinzelDecorative-Regular'),
('concertone','ConcertOne-Regular'),('cookie','Cookie-Regular'),('courgette','Courgette-Regular'),
('cousine','Cousine-Regular'),('creteround','CreteRound-Regular'),('dmserifdisplay','DMSerifDisplay-Regular'),
('fjallaone','FjallaOne-Regular'),('greatvibes','GreatVibes-Regular'),
('kaushanscript','KaushanScript-Regular'),('lato','Lato-Regular'),('lobster','Lobster-Regular'),
('pacifico','Pacifico-Regular')]

def main():
    root=Path(__file__).resolve().parents[1]/'cardforge/assets/fonts'
    def fetch(item):
        family,name=item
        folder=root/family
        folder.mkdir(parents=True,exist_ok=True)
        files={}
        for file in (name+'.ttf','OFL.txt'):
            url=f'https://raw.githubusercontent.com/google/fonts/{REV}/ofl/{family}/{file}'
            data=urllib.request.urlopen(url,timeout=60).read()
            (folder/file).write_bytes(data)
            files[file]=hashlib.sha256(data).hexdigest()
        return {'family':family,'name':name,'sha256':files}
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        manifest=list(pool.map(fetch,FONTS))
    (root/'manifest.json').write_text(json.dumps({'revision':REV,'fonts':manifest},indent=2),encoding='utf-8')
    print(f'Bundled {len(manifest)} fonts with OFL licenses.')

if __name__=='__main__':
    main()
