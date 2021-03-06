# -*- coding: utf-8 -*-
###################################################################
#
# Author: Matthew W. Boyce, PhD, boyce.matthew@epa.gov
#
# Version: 1.2 6-17-2021
#
# Description:  This script includes a number of functions that clean
#               data generated from metabolite prediction software tools:
#               OECD Toolbox, Nexus Meteor, Oasis TIMES, Biotransformer, and SyGMa.
#               Each function returns a data frame consisting of the DTXSID 
#               of the parent molecule and the metabolite's InChI key.
#               Of note, the data require SMILES to be included in each data set
#               and for cleaning OECD Toolbox data, a dictionary object 
#               with the parent molecules' QSAR ready InChI keys as keys 
#               and the DTXSID as the values.
#
# Notes: This script uses pandas, numpy, and rdkit and their dependencies
#
# Potential issues: None known
#
###################################################################

"""
Created on Tue Mar 17 10:30:53 2020

@author: MBOYCE
"""
import os as os
import pandas as pd
import numpy as np

from rdkit import Chem
from rdkit import DataStructs
from rdkit.Chem import AllChem
from rdkit.Chem import PandasTools
from rdkit.Chem import Descriptors
from rdkit.Chem import rdMolDescriptors

import sygma

def ChemReg_cleanup(file):
    df = []
    df = pd.read_csv(file, header = 0, usecols = ['Parent','Query', 'Structure_SMILES'])
    df = df.rename(columns={'Parent':'DTXSID'})    
    df = df[df['Structure_SMILES'].apply(lambda x: isinstance(x, str))]
    df['Mols'] = [Chem.MolFromSmiles(x) for x in df['Structure_SMILES']]
    df['Clean_SMILES'] = clean_SMILES(df['Structure_SMILES'])
    df['Metabolite_INCHIKEY'] = [Chem.MolToInchiKey(x) for x in df['Mols']]
    df['Reported'] = 1
    return df[['DTXSID', 'Metabolite_INCHIKEY','Clean_SMILES', 'Reported']]

def genLiteratureDF(chemRegFile, markushFile):

    df = []
    df = pd.read_csv(chemRegFile, header = 0, usecols = ['Parent','Query', 'Structure_SMILES'])
    df = df.rename(columns = {'Parent': 'Parent DTXSID', 'Query':'Metabolite DTXSID'})

    inchiKeyList = []

    for smiles in df['Structure_SMILES']:
        if isinstance(smiles, str):
            mol = Chem.MolFromSmiles(smiles)
            inchi = Chem.MolToInchi(mol)
            inchiKey = Chem.InchiToInchiKey(inchi)
        else:
            inchiKey = None
        inchiKeyList += [inchiKey]

    df['Metabolite_INCHIKEY'] = inchiKeyList
    df['Markush'] = df['Metabolite_INCHIKEY'].apply(lambda x: not isinstance(x, str))


    markushDF = pd.read_csv(markushFile, header = 0, usecols = ['Parent DTXSID','Markush DTXSID', 'JChemInchiKey'])
    markushDF = markushDF.rename(columns = {'JChemInchiKey' : 'Metabolite_INCHIKEY', 'Markush DTXSID' : 'Metabolite DTXSID'})
    markushDF['Markush'] = True
    markushDF['Metabolite_INCHIKEY'] = markushDF['Metabolite_INCHIKEY'].apply(lambda x: x[:-4]+'SA-N') #Set the ending of the JChem Inchikeys to NA-N, to standardize with RDKIT inchikeys

    mergedDF = pd.merge(df, markushDF[['Metabolite DTXSID', 'Metabolite_INCHIKEY']], on=['Metabolite DTXSID'], how='left')

    inchiList = []
    for idx in mergedDF.index:
        if not mergedDF.loc[idx,'Markush']:
            inchiList += [mergedDF.loc[idx, 'Metabolite_INCHIKEY_x']]
        else:
            inchiList += [mergedDF.loc[idx, 'Metabolite_INCHIKEY_y']]

    mergedDF['Metabolite_INCHIKEY'] = inchiList
    mergedDF = mergedDF[['Metabolite DTXSID', 'Parent DTXSID', 'Metabolite_INCHIKEY', 'Markush']]
    missingSubset = markushDF[[ID not in mergedDF['Parent DTXSID'].tolist() for ID in markushDF['Parent DTXSID']]]
    mergedDF = mergedDF.append(missingSubset, ignore_index = True)
    mergedDF = mergedDF.rename(columns = {'Parent DTXSID' : 'DTXSID'})
    mergedDF = mergedDF.dropna().drop_duplicates()
    mergedDF['Reported'] = 1
    
    return mergedDF[['DTXSID','Metabolite_INCHIKEY','Reported','Metabolite DTXSID', 'Markush']];


def TIMES_cleanup (file, Model_Module, delim = ',', header = 1):
    """Cleans data genrated by Oasis TIMES and returns a dataframe witht he DTXSID of the parent compound and InChI key of each metabolite"""
    """The Model_Module argument should be a string to designate the model used for metabolism (e.g., TIMES_RatLiver S9, TIMES_RatInVivo"""
    df = pd.read_csv(file, delimiter = delim)    
    df.rename(columns={'Chem. Name':'DTXSID'},inplace = True) 
    df = df[['DTXSID', 'Smiles']]
    df = df[header:-2]                                                                      
    df[Model_Module] = 1                                                            #Adds Times_(Model_Module) to designate model generating metabolite
    df['DTXSID'].replace({' ': np.NaN}, inplace = True)                            #Cleans DTXSID to list NaN in empty rows
    df['Metabolite_INCHIKEY'] = np.NaN                                             #Initialized column for metabolite InChI key
    metabList = df.Smiles[df['DTXSID'].isnull()]                                    #Establishes boolean list to desgiante indecies with metabolite smiles
    df['Metabolite_INCHIKEY'] = SMILES_to_InchiKey(metabList)                       #Converts metabolie SMILES to InChI keys
    df['DTXSID'] = df['DTXSID'].fillna(method = 'ffill')                            #Fills empty spaces with DTXSID, empty spaces are filled with the preceeding DTXSID
    df = df[df['Metabolite_INCHIKEY'].notnull()]                                    #Removes any all parent entries, whcih are represented as nulls in the metabolite INCHIKEY list
    df = df.drop_duplicates()  
    df[['Formula','[M+H]']] = SMILES_to_MW(df.Smiles)
    df['Clean_SMILES'] = clean_SMILES(df['Smiles'])
    return df[['DTXSID','Metabolite_INCHIKEY','Clean_SMILES','Formula','[M+H]', Model_Module]];



def Meteor_cleanup (file):
    """Cleans and returns  a dataframe for the imported OCED Toolbox metabolite data."""
    df = []
    df = pd.read_csv(file,                                                          #Reads Meteor data after it is merged into a single file
                     header = 0, 
                     usecols = ['SMILES','Name','Query Name', 'Parent'])
    df['Metabolite_INCHIKEY'] = np.NaN
    df['Meteor'] = 1                                                                #Added column to designate model that generated metabolite
    metabList = df.Parent.notnull()                                                 #Establishes boolean list of metabolites SMILES strings
    df['Metabolite_INCHIKEY'] = SMILES_to_InchiKey(df.SMILES[metabList])            #Converts metabolite SMILES to InChI keys
    df['Query Name'] = df['Query Name'].str.replace(' \([^()]*\)',"")               #Removes ' (Query)' from each DTXSID in column
    df = df.rename(columns={'Query Name':'DTXSID'})
    df = df[df.Metabolite_INCHIKEY.notnull()]                                       #Removes parent SMILES for the dataframe
    df = df.drop_duplicates()
    df['Clean_SMILES'] = clean_SMILES(df['SMILES'])
    return df[['DTXSID','Metabolite_INCHIKEY','Clean_SMILES','Meteor']];

def ToolBox_cleanup(file, DTXSIDdict, coding = 'UTF-8', delimiter = ','):
    """Cleans and returns  a dataframe for the exported OCED Toolbox metabolite data.""" 
    """"Input file requires that SMILES by exported as part of the .csv file. The DTXSDIdict argument should be a dictionary with the QSAR Ready InChI keys as the key and the DSTXID as teh value."""
    """If issues occur reading the file, try coding = 'UTF-16' and delimiter = '\t' """
    df = pd.read_csv(file, sep = delimiter,                                                      #Reads toolbox data as a tab-delimited filewith UTF-16 encoding
                     encoding = coding,                                                   #Using UTF-16 encoding due to errors in most recent file saves,
                     header = 0, usecols =                                                  #but have been able to use UTF-8 prior
                     ['SMILES','Metabolite'])
    df = df[:-2]                                                                            #Removes empty bottom row
    df = df[df.Metabolite.notnull()]                                                        #Establishes boolean list indicating indecies with metabolite
    df['Metabolite_INCHIKEY'] = SMILES_to_InchiKey(df['Metabolite'])                        #Converts metabolite SMILES to InChI keys
    df['Parent_INCHIKEY'] = SMILES_to_InchiKey(df['SMILES'],stereoisomer=False)             #Converts parent SMILES to QSAR Ready InChI keys (removes stereoisomer features during conversion)
    df['DTXSID'] = [DTXSIDdict.get(e) for e in df['Parent_INCHIKEY']]                       #Uses dictionary of parent molecules to extract 
    df['ToolBox'] = 1                                                                       #Generate column indicating the model source of the metabolite
    df = df.drop_duplicates()    
    df['Clean_SMILES'] = clean_SMILES(df['Metabolite'])                                    
    return df[['DTXSID','Metabolite_INCHIKEY','Clean_SMILES','ToolBox']];

def BioTransformer_cleanup(file, DTXSIDdict):
    """Cleans and returns a dataframe for results of BioTransformer data."""
    """Input dictionary should have the normal InChI keys (i.e., not QSAR ready) as the key and DTXSID as the value"""
    df = pd.read_csv(file, header = 0, usecols = ['InChIKey','Precursor InChIKey', 'Molecular formula','Major Isotope Mass','SMILES', 'InChI'])         #Reads metabolite InChI key and DTXSID in the file
    df = df.rename(columns = {'InChIKey':'Metabolite_INCHIKEY','Precursor InChIKey':'Parent_INCHIKEY','Molecular formula':'Formula','Major Isotope Mass':'[M+H]'})    #Renames columns
    df['DTXSID'] = [DTXSIDdict.get(e) for e in df['Parent_INCHIKEY']]
    df['DTXSID'] = df['DTXSID'].fillna(method = 'ffill')                       #Reads dictionary with Parent InChI keys are the key, and DTXSIDs as the value
    df['BioTransformer'] = 1                                                                #Generate column indicating the model source of the metabolite
    df = df.drop_duplicates()
    df['Clean_SMILES'] = clean_SMILES(df['InChI'], source = 'InChI')
    return df[['DTXSID','Metabolite_INCHIKEY','Clean_SMILES','BioTransformer']];

def CTS_cleanup(filePath, dictDTXSID):
    ctsData = pd.read_csv(filePath)    
    isParent = ctsData.routes.isnull()
    parentSMILES = ctsData.smiles[isParent]
    parentInchi = parentSMILES.apply(lambda x: Chem.MolToInchi(Chem.MolFromSmiles(x)))
    parentInchiKey = parentInchi.apply(lambda x: Chem.InchiToInchiKey(x))
    parentDTXSID = parentInchiKey.apply(lambda x: dictDTXSID[x])
    ctsData['Parent_SMILES'] = parentSMILES
    ctsData['DTXSID'] = parentDTXSID
    ctsData.loc[:,['Parent_SMILES','DTXSID']] = ctsData[['Parent_SMILES','DTXSID']].ffill()
    ctsData.dropna(inplace = True)
    ctsData['Metabolite_INCHIKEY'] = SMILES_to_InchiKey(ctsData['smiles'])
    ctsData['Clean_SMILES'] = clean_SMILES(ctsData['smiles'])
    ctsData['CTS'] = 1
    
    return ctsData[['DTXSID','Metabolite_INCHIKEY','Clean_SMILES','CTS']]


def gen_sygma_metabolites_DF(smiles_series, DTXSIDdict, pathways = [[sygma.ruleset['phase1'], 1]], keep_stereochem = True):
    metab_DF = pd.DataFrame()
    n=0
    scenario = sygma.Scenario(pathways)
    
    for smiles in smiles_series:
        mol = Chem.MolFromSmiles(smiles)
        if keep_stereochem == False:
            mol = Chem.MolFromSmiles(Chem.MolToSmiles(mol, isomericSmiles = False))
        try:
            metabolic_tree = scenario.run(mol)
            metabolic_tree.calc_scores()
        except ZeroDivisionError as error:
            print(error)
        else:
            metabolite_list = metabolic_tree.to_list()
            metabolite_DF = pd.DataFrame(metabolite_list)
            metabolite_DF['parent_smiles'] = smiles
            metabolite_DF['SyGMa_pathway'] = [e.strip() for e in metabolite_DF['SyGMa_pathway'] ]
            metabolite_DF['SyGMa_pathway'] = [e.replace(';','') for e in metabolite_DF['SyGMa_pathway'] ]
            metab_DF = metab_DF.append(metabolite_DF, ignore_index = True, sort = False)
            n+=1
        
    metab_DF['Parent_INCHIKEY'] = SMILES_to_InchiKey(metab_DF['parent_smiles'])
    metab_DF['DTXSID'] = [DTXSIDdict.get(e) for e in metab_DF['Parent_INCHIKEY']]
    metab_DF['Clean_SMILES'] = metab_DF['SyGMa_metabolite'].apply(lambda x: Chem.MolToSmiles(x, isomericSmiles = False))
    metab_DF['Metabolite_INCHIKEY'] = SMILES_to_InchiKey(metab_DF['Clean_SMILES'])
    metab_DF['SyGMa'] = 1
    metab_DF = metab_DF[metab_DF['SyGMa_pathway']!='parent']
    return metab_DF[['DTXSID','Metabolite_INCHIKEY','Clean_SMILES','SyGMa']];

def SMILES_to_InchiKey (smile_List, stereoisomer = True):
    """Uses RDKit to convert a lsit of SMILES to a list of InChI keys"""
    """If stereochemistry is not wanted (e.g., to generate QSAR Ready InChI keys, the stereoisomer argument should be set to false"""
    molList = []                                                                            #initializes a series of lists for the mols, smiles, and inchi keys
    clean_SMILES = []                                                                 
    InchiList = []
    if stereoisomer == False:                                                               #If QSAR Ready InChI Keys are needed, a SMILES without specified stereochemistry
        molList = smile_List.apply(lambda x: Chem.MolFromSmiles(x))                         #is generated from the initial set of mols. New mols are generated from the
        clean_SMILES = molList.apply(lambda x: Chem.MolToSmiles(x, isomericSmiles=False))   #stereochemistry-free SMILES, and QSAR ready InChI keys are generated from
        molList = clean_SMILES.apply(lambda x: Chem.MolFromSmiles(x))                       #the cleaned mols
        InchiList = molList.apply(lambda x: Chem.MolToInchi(x))
        InchiList = InchiList.apply(lambda x : Chem.InchiToInchiKey(x))
    else:
        molList = smile_List.apply(lambda x: Chem.MolFromSmiles(x))                         #Uses RDKit to convert SMILES to mols,
        InchiList = molList.apply(lambda x: Chem.MolToInchi(x))
        InchiList = InchiList.apply(lambda x : Chem.InchiToInchiKey(x))                     #then mols to InChI keys
    return InchiList;


def clean_SMILES (series_List, source = 'SMILES'):
    cleanSMILES = []
    mol_list = []
    if source == 'SMILES':
        mol_list = series_List.apply(lambda x: Chem.MolFromSmiles(x))
    elif source == 'InChI':
        mol_list = series_List.apply(lambda x: Chem.MolFromInchi(x, sanitize = False))  #Sanitize turned off as some smiles generated by prediction software were not appropriately assigning
    cleanSMILES = mol_list.apply(lambda x: Chem.MolToSmiles(x, isomericSmiles=False))   #positive charges to protonated amines. This issue is carried throughout the code, and is affected 
    return cleanSMILES;                                                                 #smiles are marked as 'Incompatible SMILES' when calculating molecular formula and weight.

def SMILES_to_MW (smile_List):
    molList = []
    MH_list = []
    molForm_list = []
    mass_H = Descriptors.ExactMolWt(Chem.MolFromSmiles('[H+]'))
    molList = smile_List.apply(lambda x: Chem.MolFromSmiles(x))
    MH_list = molList.apply(lambda x: Descriptors.ExactMolWt(x) + mass_H)
    molForm_list = molList.apply(lambda x: rdMolDescriptors.CalcMolFormula(x))
    data = pd.DataFrame({'Formula':molForm_list, '[M+H]':MH_list})
    return data;

def aggregate_DFs(DF_List, arg_on = ['DTXSID','Metabolite_INCHIKEY'], arg_how = 'outer'):
    excludedColumns = ['Clean_SMILES']
    numDF = len(DF_List)
    if numDF < 2:
        return
    try:
        agg_DF = DF_List[0].drop(excludedColumns, axis = 1)
    except:
        agg_DF = DF_List[0]

    comp_DF = DF_List[1:]

    for DF in range(len(comp_DF)):
        addDF = comp_DF[DF]
        try:
            addDF = addDF.drop(excludedColumns, axis = 1)
        except:
            addDF = addDF

        agg_DF = pd.merge(agg_DF, addDF, on = arg_on, how = arg_how)
        agg_DF = agg_DF.replace(np.NaN, 0)
        
    agg_DF.drop_duplicates(inplace = True, ignore_index = True)

    return agg_DF

#Aggregate all data single dataframe by iteratively combining dataframes
def aggregate_DFs_extended(DF_list, arg_on = ['DTXSID','Metabolite_INCHIKEY'], arg_how = 'outer'):
    numDF = len(DF_list)
    if numDF < 2:
        return
    agg_DF = DF_list[0]
    comp_DF = DF_list[1:]
    for DF in range(len(comp_DF)):
        agg_DF = pd.merge(agg_DF, comp_DF[DF], on = arg_on, how = arg_how)
        agg_DF = agg_DF.replace(np.NaN, 0)
    tmp_SMILES_cols = [col for col in agg_DF.columns if 'Clean_SMILES' in col]
    all_smiles = agg_DF.loc[:,tmp_SMILES_cols]
    all_smiles.replace(0,np.NaN, inplace = True)
    mode_smiles = all_smiles.mode(axis = 1, dropna = True)
    agg_DF['SMILES'] = mode_smiles[0]
    agg_DF.drop(columns = tmp_SMILES_cols, inplace = True)
    agg_DF.drop_duplicates(inplace = True, ignore_index = True)
    
    molList = agg_DF['SMILES'].apply(lambda x: Chem.MolFromSmiles(x))
    Null_values = molList[molList.isnull()].apply(lambda x: 'Incompatible SMILES')  #Check for Incompatible SMILES. Some prediction softwares will not appropriately assign charges, 
    mass_H = Descriptors.ExactMolWt(Chem.MolFromSmiles('[H+]'))                     #This will stop the code from erroring out if the SMILES incorrect
    
    MH_list = molList[molList.notnull()].apply(lambda x: Descriptors.ExactMolWt(x) + mass_H)
    MH_series_for_DF = pd.concat([MH_list,Null_values]).sort_index()
    agg_DF['[M+H]'] = MH_series_for_DF
    
    Formula_list = molList[molList.notnull()].apply(lambda x: rdMolDescriptors.CalcMolFormula(x))
    Formula_series_for_DF = pd.concat([Formula_list,Null_values]).sort_index()
    agg_DF['Formula'] = Formula_series_for_DF
        
    return agg_DF
        

#####Example of run sequenc to process the a set of data using original CopTox file and model outputs
###Set directory of files exported from each of the models
#os.chdir('C:\\Users\\MBOYCE\\Documents\\ExpoCast_39CompData\\All Data\\')
    
#####Import starting DSSToxID data and intializes dictionary for importing ToolBox data
#DSSToxList = pd.read_csv("CompToxList.csv", header = 0)
#DSSToxList = DSSToxList.rename(columns={'INCHIKEY':'Parent_INCHIKEY'})
#DSSToxList['QSAR_READY_INCHIKEY'] = SMILES_to_InchiKey(DSSToxList['QSAR_READY_SMILES'],stereoisomer = False)
#Norm_DTXSID_dict = dict(zip(DSSToxList['Parent_INCHIKEY'],DSSToxList['DTXSID']))
#QSAR_DTXSID_dict = dict(zip(DSSToxList['QSAR_READY_INCHIKEY'],DSSToxList['DTXSID']))

#####Import and clean up each DF
# toolBoxDF = ToolBox_cleanup('ToolBox_Report.csv', QSAR_DTXSID_dict)
# meteorDF = Meteor_cleanup('Meteor_Report.csv')
# bioTransformerDF = BioTransformer_cleanup('BioTransformer_Report.csv', Norm_DTXSID_dict)
# times_inVivoDF = TIMES_cleanup('TIMES_invivo.txt', 'TIMES_InVivo')
# times_inVitroDF = TIMES_cleanup('TIMES_invitro.txt', 'TIMES_InVitro')

######Combine DFs into a list, and aggregate DFs into single file
# dfList = [toolBoxDF, meteorDF, bioTransformerDF,times_inVivoDF, times_inVitroDF]
# agg_Data = aggregate_DFs(dfList)

#Sensitivity Calculations
# True Predictions / All Reported

def sumMarkParents(dataFrame, modelFilter):
    """Filters dataframe to only rows that have markush structures, then returns 1 for each markush structure:parent DTXSID pairing if one 
    or more of the children are predicted by the correpsonding modelName argument.
    
    Returns a sum of all markush parents
    """   
    markDF = dataFrame[dataFrame['Markush'] == True]
    sumReducedMark = 0
    par_metabMatch = zip(markDF['DTXSID'], markDF['Metabolite DTXSID'])
    uniqueMatch = list(set(par_metabMatch))
    for par, metab in uniqueMatch:
        parFilter = markDF['DTXSID'] == par
        metabFilter = markDF['Metabolite DTXSID'] == metab
        sumPredicted = sum(parFilter & metabFilter & modelFilter)
        if sumPredicted > 0:
            sumReducedMark += 1
    
    return sumReducedMark

def calcSensitivity(data, modelName):
    """Calculates the Sensitivity of the entered data DF set using the a single modelName string, or list of strings that
    correspond to the columns in the data DF.
    
    Sensitivity = True Predictions / All Reported
    
    Returns a sum of all predicted markush parents
    """
    
    #Determine if a str or list is being entered for the modelNames, providing a list will yield sensitivity across the combined models
    if isinstance(modelName, list):
        modelFilter = data[modelName[0]] == 1
        if len(modelName) > 1:
            for model in modelName[1:]:
                modelFilter = modelFilter | data[model] == 1 
    elif isinstance(modelName, str):
        modelFilter = data[modelName] == 1
        
    
        
    reportFilter = data['Reported'] == 1
    markFilter = data['Markush'] == True
    trueNonMark = sum(modelFilter & reportFilter & ~markFilter)      ## True metabolites that are not markush structures
    trueMarkParent = sumMarkParents(data, modelFilter)               ## True metabolites that have a common parent structure
    reportNonMark = sum(reportFilter & ~markFilter)                  ## Reported metabolites that are not markush structures
    
    reportMarkParent = len(set(zip(data.loc[reportFilter & markFilter, 'DTXSID'], data.loc[reportFilter & markFilter, 'Metabolite DTXSID'])))  ## Reported metabolites that have a common marksuh parent (unique 
                                                                                                                                               ## Paent:Metabolite DTXSID)
    Sensitivity = round((trueNonMark + trueMarkParent)/(reportNonMark + reportMarkParent), 3)
    return Sensitivity

def calcPrecision(data, modelName): #Update name to sensitivity
    """Calculates the prediction of the data using a single str or list of strings in the modelName argument. The modelName corresponds to
    the columns to be analyzed.
    
    Sensitivity Formula: True Predictions / All Prediction
    """  

    if isinstance(modelName, list):
        modelFilter = data[modelName[0]] == 1
        if len(modelName) > 1:
            for model in modelName[1:]:
                modelFilter = modelFilter | data[model] == 1
                
    else:
        modelFilter = data[modelName] == 1
    
    
    reportFilter = data['Reported'] == 1
    
    truePred = sum(modelFilter & reportFilter)
    allPred = sum(modelFilter)
    
    if(allPred > 0):
        Precision = round(truePred / allPred, 3)
    
    elif (allPred == 0 & truePred == 0):
        Precision = 0.0
    
    return Precision



def autolabel(rects, ax, xPos='center'):
    """
    Attach a text label above each bar in *rects*, displaying its height.

    *xpos* indicates which side to place the text w.r.t. the center of
    the bar. It can be one of the following {'center', 'right', 'left'}.
    """
    
    xPos = xPos.lower()  # normalize the case of the parameter
    ha = {'center': 'center', 'right': 'left', 'left': 'right'}
    offset = {'center': 0.5, 'right': 0.57, 'left': 0.43}  # x_txt = x + w*off

    for rect in rects:
        height = rect.get_height()
        ax.text(rect.get_x() + rect.get_width()*offset[xPos], 0.9*height,
                '{}'.format(height), ha=ha[xPos], va='bottom')


