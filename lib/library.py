import os, subprocess, logging, sys, argparse, inspect, csv, time
import warnings
from Bio import SeqIO
with warnings.catch_warnings():
    warnings.simplefilter('ignore')
    from Bio import SearchIO

#get the working directory, so you can move back into DB folder to find the files you need
currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0,parentdir)
DB = os.path.join(parentdir, 'DB')

class colr:
    GRN = '\033[92m'
    END = '\033[0m'
    WARN = '\033[93m'

def multipleReplace(text, wordDict):
    for key in wordDict:
        text = text.replace(key, wordDict[key])
    return text

def which(name):
    try:
        with open(os.devnull) as devnull:
            if not name == 'tbl2asn':
                subprocess.Popen([name], stdout=devnull, stderr=devnull).communicate()
            else:
                subprocess.Popen([name, '--version'], stdout=devnull, stderr=devnull).communicate()
    except OSError as e:
        if e.errno == os.errno.ENOENT:
            return False
    return True

def line_count(fname):
    with open(fname) as f:
        for i, l in enumerate(f):
            pass
    return i + 1

def setupLogging(LOGNAME):
    global log
    if 'win32' in sys.platform:
        stdoutformat = logging.Formatter('%(asctime)s: %(message)s', datefmt='[%I:%M:%S %p]')
    else:
        stdoutformat = logging.Formatter(colr.GRN+'%(asctime)s'+colr.END+': %(message)s', datefmt='[%I:%M:%S %p]')
    fileformat = logging.Formatter('%(asctime)s: %(message)s')
    log = logging.getLogger(__name__)
    log.setLevel(logging.DEBUG)
    sth = logging.StreamHandler()
    sth.setLevel(logging.INFO)
    sth.setFormatter(stdoutformat)
    log.addHandler(sth)
    fhnd = logging.FileHandler(LOGNAME)
    fhnd.setLevel(logging.DEBUG)
    fhnd.setFormatter(fileformat)
    log.addHandler(fhnd)

def countfasta(input):
    count = 0
    with open(input, 'rU') as f:
        for line in f:
            if line.startswith (">"):
                count += 1
    return count

def SwissProtBlast(input, cpus, evalue, tmpdir, output):
    FNULL = open(os.devnull, 'w')
    #run blastp against uniprot
    blast_tmp = os.path.join(tmpdir, 'uniprot.xml')
    blastdb = os.path.join(DB,'uniprot')
    subprocess.call(['blastp', '-db', blastdb, '-outfmt', '5', '-out', blast_tmp, '-num_threads', str(cpus), '-max_target_seqs', '1', '-evalue', str(evalue), '-query', input], stdout = FNULL, stderr = FNULL)

    #parse results
    with open(output, 'w') as output:
        with open(blast_tmp, 'rU') as results:
            for qresult in SearchIO.parse(results, "blast-xml"):
                hits = qresult.hits
                qlen = qresult.seq_len
                ID = qresult.id
                num_hits = len(hits)
                if num_hits > 0:
                    length = hits[0].hsps[0].aln_span
                    pident = hits[0].hsps[0].ident_num / float(length)
                    if pident < 0.6:
                        continue
                    diff = length / float(qlen)
                    if diff < 0.6:
                        continue
                    description = hits[0].description.split("=")
                    hdescript = description[0].replace(' OS','')
                    #species = description[1].replace(' GN','')
                    name = description[2].replace(' PE','').upper()
                    #okay, print out annotations for GAG
                    if ID.endswith('-T1'):
                        output.write("%s\tproduct\t%s\n" % (ID,hdescript))
                        geneID = ID.replace('-T1','')
                        output.write("%s\tname\t%s\n" % (geneID,name))
                    else:
                        output.write("%s\tname\t%s\n" % (ID,name))
                        mrnaID = ID + '-T1'
                        output.write("%s\tproduct\t%s\n" % (mrnaID,hdescript))

def MEROPSBlast(input, cpus, evalue, tmpdir, output):
    FNULL = open(os.devnull, 'w')
    #run blastp against uniprot
    blast_tmp = os.path.join(tmpdir, 'merops.xml')
    blastdb = os.path.join(DB,'MEROPS')
    subprocess.call(['blastp', '-db', blastdb, '-outfmt', '5', '-out', blast_tmp, '-num_threads', str(cpus), '-max_target_seqs', '1', '-evalue', str(evalue), '-query', input], stdout = FNULL, stderr = FNULL)

    #parse results
    with open(output, 'w') as output:
        with open(blast_tmp, 'rU') as results:
            for qresult in SearchIO.parse(results, "blast-xml"):
                hits = qresult.hits
                qlen = qresult.seq_len
                ID = qresult.id
                num_hits = len(hits)
                if num_hits > 0:
                    if hits[0].hsps[0].evalue > evalue:
                        continue
                    sseqid = hits[0].id
                    family = hits[0].description
                    #okay, print out annotations for GAG
                    output.write("%s\tnote\tMEROPS:%s %s\n" % (ID,sseqid,family))


def runEggNog(file, cpus, evalue, tmpdir, output):
    FNULL = open(os.devnull, 'w')
    #run hmmerscan
    HMM = os.path.join(DB, 'fuNOG_4.5.hmm')
    eggnog_out = os.path.join(tmpdir, 'eggnog.txt')
    subprocess.call(['hmmscan', '-o', eggnog_out, '--cpu', str(cpus), '-E', str(evalue), HMM, file], stdout = FNULL, stderr = FNULL)

    #load in annotation dictionary
    EggNog = {}
    with open(os.path.join(DB,'fuNOG.annotations.tsv'), 'rU') as input:
        reader = csv.reader(input, delimiter='\t')
        for line in reader:
            EggNog[line[1]] = line[5]

    #now parse results
    with open(output, 'w') as output:
        with open(eggnog_out, 'rU') as results:
            for qresult in SearchIO.parse(results, "hmmer3-text"):
                query_length = qresult.seq_len
                lower = query_length * 0.50
                upper = query_length * 1.50
                hits = qresult.hits
                num_hits = len(hits)
                if num_hits > 0:
                    for i in range(0,num_hits):
                        if hits[i].domain_exp_num != hits[i].domain_obs_num: #make sure # of domains is correct
                            continue
                        aln_length = 0
                        num_hsps = len(hits[i].hsps)
                        for x in range(0,num_hsps):
                            aln_length += hits[i].hsps[x].aln_span
                        if aln_length < lower or aln_length > upper: #make sure most of the protein aligns to the model
                            continue
                        hit = hits[i].id.split(".")[1]
                        query = hits[i].query_id
                        #look up descriptions in annotation dictionary
                        description = EggNog.get(hit)
                        final_result = hit + ': ' + description
                        output.write("%s\tnote\t%s\n" % (query, final_result))
                        break

def PFAMsearch(input, cpus, evalue, tmpdir, output):
    FNULL = open(os.devnull, 'w')
    #run hmmerscan
    HMM = os.path.join(DB, 'Pfam-A.hmm')
    pfam_out = os.path.join(tmpdir, 'pfam.txt')
    pfam_filtered = os.path.join(tmpdir, 'pfam.filtered.txt')
    subprocess.call(['hmmscan', '--domtblout', pfam_out, '--cpu', str(cpus), '-E', str(evalue), HMM, input], stdout = FNULL, stderr = FNULL)
    #now parse results
    with open(output, 'w') as output:
        with open(pfam_filtered, 'w') as filtered:
            with open(pfam_out, 'rU') as results:
                for qresult in SearchIO.parse(results, "hmmscan3-domtab"):
                    query_length = qresult.seq_len
                    hits = qresult.hits
                    num_hits = len(hits)
                    if num_hits > 0:
                        for i in range(0,num_hits):
                            hit_evalue = hits[i].evalue
                            if hit_evalue > evalue:
                                continue
                            hit = hits[i].id
                            pfam = hits[i].accession.split('.')[0]
                            hmmLen = hits[i].seq_len
                            hmm_aln = int(hits[i].hsps[0].hit_end) - int(hits[i].hsps[0].hit_start)
                            coverage = hmm_aln / float(hmmLen)
                            if coverage < 0.50: #coverage needs to be at least 50%
                                continue
                            query = hits[i].query_id
                            description = hits[i].description
                            filtered.write("%s\t%s\t%s\t%s\t%f\n" % (query, pfam, description, hit_evalue, coverage))
                            output.write("%s\tdb_xref\tPFAM:%s\n" % (query, pfam))



def dbCANsearch(input, cpus, evalue, tmpdir, output):
    CAZY = {'CBM': 'Carbohydrate-binding module', 'CE': 'Carbohydrate esterase','GH': 'Glycoside hydrolase', 'GT': 'Glycosyltransferase', 'PL': 'Polysaccharide lyase', 'AA': 'Auxillary activities'}
    FNULL = open(os.devnull, 'w')
    #run hmmerscan
    HMM = os.path.join(DB, 'dbCAN.hmm')
    dbCAN_out = os.path.join(tmpdir, 'dbCAN.txt')
    dbCAN_filtered = os.path.join(tmpdir, 'dbCAN.filtered.txt')
    subprocess.call(['hmmscan', '--domtblout', dbCAN_out, '--cpu', str(cpus), '-E', str(evalue), HMM, input], stdout = FNULL, stderr = FNULL)

    #now parse results
    with open(output, 'w') as output:
        with open(dbCAN_filtered, 'w') as filtered:
            filtered.write("#HMM_family\tHMM_len\tQuery_ID\tQuery_len\tE-value\tHMM_start\tHMM_end\tQuery_start\tQuery_end\tCoverage\n")
            with open(dbCAN_out, 'rU') as results:
                for qresult in SearchIO.parse(results, "hmmscan3-domtab"):
                    query_length = qresult.seq_len
                    hits = qresult.hits
                    num_hits = len(hits)
                    if num_hits > 0:
                        for i in range(0,num_hits):
                            hit_evalue = hits[i].evalue
                            if hit_evalue > evalue:
                                continue
                            hit = hits[i].id
                            hmmLen = hits[i].seq_len
                            hmm_aln = int(hits[i].hsps[0].hit_end) - int(hits[i].hsps[0].hit_start)
                            coverage = hmm_aln / float(hmmLen)
                            if coverage < 0.45:
                                continue
                            query = hits[i].query_id
                            filtered.write("%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%f\n" % (hit, hmmLen, query, query_length, hit_evalue, hits[i].hsps[0].hit_start, hits[i].hsps[0].hit_end, hits[i].hsps[0].query_start, hits[i].hsps[0].query_end, coverage))
                            #get type of hit for writing the annotation note
                            type = ''.join(i for i in hit if not i.isdigit())
                            descript = CAZY.get(type)
                            output.write("%s\tnote\t%s enzyme from CAZy family %s\n" % (query, descript, hit))

def fCEGMA(input, cpus, evalue, tmpdir, gff, output):
    FNULL = open(os.devnull, 'w')
    #now run hmmsearch against fCEGMA models
    fCEGMA_HMM = os.path.join(DB, 'fCEGMA.hmm')
    temp_out = os.path.join(tmpdir, 'fCEGMA.hmmsearch.txt')
    subprocess.call(['hmmsearch', '-o', temp_out, '-E', str(evalue), '--cpu', str(cpus), fCEGMA_HMM, input], stdout = FNULL, stderr = FNULL)
    #now parse results, getting only high quality matches
    keep = {}
    with open(output, 'w') as output:
        with open(temp_out, 'rU') as results:
            for qresult in SearchIO.parse(results, "hmmer3-text"):
                hits = qresult.hits
                model = qresult.id
                #here we just want the best hit for each model
                if len(hits) > 0:
                    beste = hits[0].evalue
                    if beste >= evalue:
                        continue
                    model_length = qresult.seq_len
                    hit_start = hits[0].hsps[0].hit_start
                    hit_end = hits[0].hsps[0].hit_end
                    hit_aln = hit_end - hit_start
                    coverage = hit_aln / float(model_length)
                    if coverage < 0.9:
                        continue
                    hit = hits[0].id
                    if hit not in keep:
                        keep[hit] = model
                    output.write("%s\t%s\t%s\t%s\t%s\t%s\t%f\n" % (hit, model, beste, model_length, hit_start, hit_end, coverage))

    #loop through genemark GFF3 and pull out genes, rename to 'MODEL', and then slice to just get those that pass.
    for key, value in keep.items():
        keep[key] = value + "-T1"
        new_key = key.replace("_t", "_g")
        keep[new_key] = value
    import re
    pattern = re.compile(r'\b(' + '|'.join(keep.keys()) + r')\b')
    gff_out = os.path.join(tmpdir, 'training.gff3')
    with open(gff_out, 'w') as output:
        with open(gff, 'rU') as input:
            for line in input:
                line = pattern.sub(lambda x: keep[x.group()], line)
                if 'MODEL' in line:
                    output.write(line)

def RepeatModelMask(input, cpus, tmpdir, output):
    log.info("Loading sequences and soft-masking genome")
    FNULL = open(os.devnull, 'w')
    input = os.path.abspath(input)
    output = os.path.abspath(output)
    #lets run RepeatModeler here to get repeat library
    if not os.path.exists('RepeatModeler'):
        os.makedirs('RepeatModeler')
    log.info("Soft-masking: building RepeatModeler database")
    subprocess.call(['BuildDatabase', '-name', tmpdir, input], cwd='RepeatModeler', stdout = FNULL, stderr = FNULL)
    log.info("Soft-masking: generating repeat library using RepeatModeler")
    subprocess.call(['RepeatModeler', '-database', tmpdir, '-pa', str(cpus)], cwd='RepeatModeler', stdout = FNULL, stderr = FNULL)
    #find name of folder
    for i in os.listdir('RepeatModeler'):
        if i.startswith('RM_'):
            RP_folder = i
    library = os.path.join(tmpdir, 'repeatmodeler.lib.fa')
    library = os.path.abspath(library)
    #os.rename(os.path.join('RepeatModeler', RP_folder, 'consensi.fa.classified'), library)

    #now soft-mask the genome for gene predictors
    log.info("Soft-masking: running RepeatMasker with custom library")
    if not os.path.exists('RepeatMasker'):
        os.makedirs('RepeatMasker')
    subprocess.call(['RepeatMasker', '-lib', library, '-pa', str(cpus), '-xsmall', '-dir', 'RepeatMasker', input], stdout=FNULL, stderr=FNULL)
    for file in os.listdir('RepeatMasker'):
        if file.endswith('.masked'):
            os.rename(os.path.join('RepeatMasker', file), os.path.join(tmpdir, output))
        if file.endswith('.out'):
            rm_gff3 = output.split('.softmasked.fa')[0]
            rm_gff3 = rm_gff3 + '.repeatmasked.gff3'
            rm_gff3 = os.path.join(tmpdir, rm_gff3)
            with open(rm_gff3, 'w') as output:
                subprocess.call(['rmOutToGFF3.pl', file], cwd='RepeatMasker', stdout = output, stderr = FNULL)


def CheckAugustusSpecies(input):
    #get the possible species from augustus
    augustus_list = []
    for i in os.listdir(os.path.join(os.environ["AUGUSTUS_CONFIG_PATH"], 'species')):
        if not i.startswith('.'):
            augustus_list.append(i)
    augustus_list = set(augustus_list)
    if input in augustus_list:
        return True
    else:
        return False

def CheckDependencies(input):
    missing = []
    for p in input:
        if which(p) == False:
            missing.append(p)
    if missing != []:
        error = ", ".join(missing)
        log.error("Missing Dependencies: %s.  Please install missing dependencies and re-run script" % (error))
        sys.exit(1)

def SortRenameHeaders(input, output):
    #sort records and write temp file
    with open(output, 'w') as output:
        with open(input, 'rU') as input:
            records = list(SeqIO.parse(input, 'fasta'))
            records.sort(cmp=lambda x,y: cmp(len(y),len(x)))
            counter = 1
            for rec in records:
                rec.name = ''
                rec.description = ''
                rec.id = 'scaffold_' + str(counter)
                counter +=1
            SeqIO.write(records, output, 'fasta')

def RunGeneMarkES(input, cpus, tmpdir, output):
    FNULL = open(os.devnull, 'w')
    #make directory to run script from
    if not os.path.exists('genemark'):
        os.makedirs('genemark')
    contigCount = countfasta(input)
    log.info('Loading genome assembly: ' + '{0:,}'.format(contigCount) + ' contigs')
    contigs = os.path.abspath(input)
    log.info("Running GeneMark-ES on assembly")
    log.debug("gmes_petap.pl --ES --fungus --cores %i --sequence %s" % (cpus, contigs))
    subprocess.call(['gmes_petap.pl', '--ES', '--fungus', '--cores', str(cpus), '--sequence', contigs], cwd='genemark', stdout = FNULL, stderr = FNULL)
    os.rename(os.path.join('genemark','output','gmhmm.mod'), os.path.join(tmpdir, 'gmhmm.mod'))
    #convert genemark gtf to gff3 so GAG can interpret it
    gm_gtf = os.path.join('genemark', 'genemark.gtf')
    log.info("Converting GeneMark GTF file to GFF3")
    with open(output, 'w') as gff:
        subprocess.call(['genemark_gtf2gff3', gm_gtf], stdout = gff)

def MemoryCheck():
    from psutil import virtual_memory
    mem = virtual_memory()
    RAM = int(mem.total)
    return round(RAM / 1024000000)

