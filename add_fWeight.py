
import re
import sys

def read_file(infile):
    '''Reads a file and returns a list'''
    lines = []
    with open(infile, 'r') as f:
        lines = f.readlines()
    return lines

def read_simc_histfile(histfile):
    '''Reads SIMC hist file and returns a dictionary'''
    result = {}
    regex = r"\s+([A-Za-z\s{0,1}\(\)/_\.>]+)\s+=\s+([0-9E?\+?\.-]+)"
    lines = read_file(histfile)
    for line in lines:
        if 'GeV^2' not in line:
            temp = re.findall(regex, line)
            if temp: result[temp[0][0].strip()] = temp[0][1]
    return result

def grab_simc_norm_factor(histfile):
    '''Grabs important normalization factors from SIMC .hist file'''
    histentry = read_simc_histfile(histfile)

    normfact = histentry.get('normfac',0)
    ngenrequest = histentry.get('Ngen (request)',0)

    fnorm = float(normfact)/float(ngenrequest)
    return fnorm

def add_fWeight(infile, simcnorm):
    '''Adds fWeight to the SIMC ROOT file'''
    import subprocess
    try:
        subprocess.run(
            ["root", "-l", "-b", "-q",
            f'add_fWeight.cpp("{infile}",{simcnorm})'],
            check=True
        )
    except FileNotFoundError:
        print("ERROR: ROOT not found. Is the ROOT module loaded?")
    except subprocess.CalledProcessError:
        print("ERROR: add_fWeight.cpp failed.")

def main():
    if len(sys.argv) != 2:
        print("Usage: python add_fWeight.py <histfile>")
        sys.exit(1)

    histfile = sys.argv[1]
    fnorm = grab_simc_norm_factor(histfile)
    print(f"SIMC norm factor: {fnorm}")
    rootfile = histfile.replace('.hist', '.root').replace('outfiles/', 'worksim/') 
    add_fWeight(rootfile, fnorm)

if __name__ == "__main__":
    main()