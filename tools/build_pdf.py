"""纯文字宋体 11 号 PDF。需要 reportlab、pdfplumber、pypdfium2。"""
from pathlib import Path
import re
import shutil
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
import pdfplumber
import pypdfium2 as pdfium
from PIL import Image,ImageOps

ROOT=Path(__file__).resolve().parents[1]
FONT='P6Song';SIZE=11;LEADING=16;MARGIN=44
WIDTH,HEIGHT=A4


def plain(text):
    lines=[]
    for line in text.splitlines():
        if line.startswith('```'):continue
        line=re.sub(r'^#+\s*','',line).replace('`','')
        lines.append(line)
    return '\n'.join(lines)


def wrap(text):
    if not text:return ['']
    result=[];line='';width=WIDTH-2*MARGIN
    continuation='    ' if text.startswith(' ') else ''
    # 宋体的西文为半角；不裁切长 RTL 行。
    for token in re.findall(r'[A-Za-z0-9_$]+|.',text):
        if line and pdfmetrics.stringWidth(line+token,FONT,SIZE)>width:
            result.append(line.rstrip());line=continuation
        line+=token
    if line:result.append(line.rstrip())
    return result


def build(name):
    source=(ROOT/name).read_text(encoding='utf-8')
    blocks=re.split(r'(?=^## [QM]\d\d)',source,flags=re.M)
    output=ROOT/name.replace('.md','.pdf')
    document=canvas.Canvas(str(output),pagesize=A4,pageCompression=1)
    document.setTitle(plain(source.splitlines()[0]));document.setAuthor('')
    y=HEIGHT-MARGIN-SIZE;pages=1;source_text=[]
    def new_page():
        nonlocal y,pages
        document.showPage();pages+=1;y=HEIGHT-MARGIN-SIZE;document.setFont(FONT,SIZE)
    document.setFont(FONT,SIZE)
    for block in blocks:
        text=plain(block).strip();source_text.append(text)
        lines=[line for raw in text.splitlines() for line in wrap(raw)]
        capacity=int((HEIGHT-2*MARGIN-SIZE)//LEADING)+1
        if len(lines)<=capacity and y-(len(lines)-1)*LEADING<MARGIN:new_page()
        for line in lines:
            if y<MARGIN:new_page()
            document.drawString(MARGIN,y,line);y-=LEADING
        y-=LEADING
    document.save()
    with pdfplumber.open(output) as pdf:
        extracted=[]
        for p in pdf.pages:
            assert not p.images and not p.rects and not p.curves
            assert {round(c['size'],2) for c in p.chars}=={SIZE}
            assert all(c['x0']>=MARGIN-.1 and c['x1']<=WIDTH-MARGIN+.1 for c in p.chars)
            assert all(c['top']>=MARGIN-.1 and c['bottom']<=HEIGHT-MARGIN+.1 for c in p.chars)
            extracted.append(p.extract_text())
        normalize=lambda x:''.join(x.split())
        assert normalize('\n'.join(extracted))==normalize('\n'.join(source_text))
    preview=ROOT.parent/'tmp'/'pdfs'/'p6_book_v2';preview.mkdir(parents=True,exist_ok=True)
    doc=pdfium.PdfDocument(str(output));thumbs=[]
    for i in range(len(doc)):
        image=doc[i].render(scale=1.25).to_pil().convert('RGB')
        if i in (0,1,len(doc)-1) or 'sbc' in extracted[i]:image.save(preview/(output.stem+f'_{i+1}.png'))
        image.thumbnail((280,400));thumbs.append(ImageOps.expand(image,border=1,fill='#bbb'))
    columns=4;rows=(len(thumbs)+columns-1)//columns
    board=Image.new('RGB',(columns*302,rows*424),'white')
    for i,thumb in enumerate(thumbs):board.paste(thumb,(10+i%columns*302,10+i//columns*424))
    board.save(preview/(output.stem+'_总览.png'))
    output_dir=ROOT.parent/'output'/'pdf';output_dir.mkdir(parents=True,exist_ok=True)
    shutil.copy2(output,output_dir/output.name)
    print(output.name,pages,'pages; text/layout verified',flush=True)


def main():
    font=TTFont(FONT,'C:/Windows/Fonts/simsun.ttc',subfontIndex=0);pdfmetrics.registerFont(font)
    for name in ('P6_历年课上题_题目册.md','P6_模拟上机题目册.md'):build(name)


if __name__=='__main__':main()
