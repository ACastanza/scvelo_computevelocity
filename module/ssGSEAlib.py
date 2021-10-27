# Copyright (c) 2012-2020 Broad Institute, Inc., Massachusetts Institute of Technology, and Regents of the University of California.  All rights reserved.
#
# Projects gene expression data or ATARiS consistency scores (in either
# case, encoded in GCT input files) to gene set enrichment scores.
# (note: for clarity comments will mostly refer to expression data)
#
# Original Authors:
# Pablo Tamayo, Chet Birger
# Reimplementation in Python, and additional Helper functions by:
# Anthony S. Castanza
#


def ssGSEA_project_dataset(
    # name of gct input file containing
    # gene expression data
    input_ds,
    # name of gct output file name containing
    # single-sample gene-set enrichment scores
    output_ds,
    # list of full pathnames of gmt input files
    # containing gene set definitions
    gene_sets_dbfile_list,
    # column containing gene symbols within gct input file
    #  "Name", "Description"
    gene_symbol_column="Name",
    # "ALL" or list with names of gene sets
    gene_set_selection="ALL",
    # normalization method applied to input feature data:
    # "none", "rank", "log" or "log.rank"
    sample_norm_type="none",
    # exponential weight applied to ranking in calculation of
    # enrichment score
    weight=0.75,
    # "combine.off" do not combine *_UP and *_DN versions in
    #   a single score. "combine.replace" combine *_UP and
    #   *_DN versions in a single score that replaces the individual
    # *_UP and *_DN versions. "combine.add" combine *_UP and
    # *_DN versions in a single score and add it but keeping
    # the individual *_UP and *_DN versions.
    combine_mode="combine.add",
    # min overlap required between genes in gene set and genes in input (feature
    # dataset) file in order to include that gene set in data set projection
    min_overlap=1):
    import sys
    import pandas as pd
    import numpy as np
    import ssGSEAlib

    # validate input parameters
    if gene_symbol_column != "Name" and gene_symbol_column != "Description":
        sys.exit("invalid value for gene.symbol.column argument: " +
                 gene_symbol_column)

    if sample_norm_type != "none" and sample_norm_type != "rank" and sample_norm_type != "log" and sample_norm_type != "log.rank":
        sys.exit("invalid value for sample.norm.type.argument: " +
                 sample_norm_type)

    if combine_mode != "combine.off" and combine_mode != "combine.replace" and combine_mode != "combine.add":
        sys.exit("invalid value for combine.mode argument: ", combine_mode)

    # Read input dataset (GCT format)
    dataset = ssGSEAlib.read_gct(input_ds)
    m = dataset['data'].copy()

    # "Name" refers to column 1; "Description" to column 2
    # in Ataris or hairpin gct files the gene symbols are column 2
    if gene_symbol_column.upper() == "NAME":
        gene_names = m.index.tolist()
    elif gene_symbol_column == "Description":
        gene_names = dataset['row_descriptions'].tolist()
        m.index = gene_names
        m.index.names = ["NAME"]

    gene_descs = dataset['row_descriptions'].tolist()
    sample_names = m.columns.to_list()

    Ns = len(m.iloc[0])  # Number of Samples
    Ng = len(m.iloc[:, 0])  # Number of Genes

    # Sample normalization
    if sample_norm_type == "none":
        print("No normalization to be made")
    elif sample_norm_type == "rank":
        for j in range(Ns):  # column rank normalization
            m.iloc[:, j] = m.iloc[:, j].rank(method="average")
        m = 10000 * m / Ng
    elif sample_norm_type == "log.rank":
        for j in range(Ns):  # column rank normalization
            m.iloc[:, j] = m.iloc[:, j].rank(method="average")
        m = np.log(10000 * m / Ng + np.exp(1))
    elif sample_norm_type == "log":
        m[m < 1] = 1
        m = np.log(m + np.exp(1))

    # Read gene set databases

    # identify largest gene set size (max.G) and total number of
    # gene sets across all databases (max.N)
    max_G = 0
    max_N = 0
    for gsdb in gene_sets_dbfile_list:
        gsdb_split = gsdb.split(".")
        if gsdb_split[-1] == "gmt":
            GSDB = ssGSEAlib.read_genesets_gmt(
                gsdb, thres_min=2, thres_max=2000)
        else:  # is a gmx formatted file
            GSDB = rssGSEAlib.ead_genesets_gmx(
                gsdb, thres_min=2, thres_max=2000)
        max_G = max(max_G, max(GSDB['size_G']))
        max_N = max_N + GSDB['N_gs']

    # create matrix (gs) containing all gene set definitions
    N_gs = 0
    gs = pd.DataFrame(np.nan, index=range(max_N), columns=range(max_G))
    gs_names = list(range(max_N))
    gs_descs = list(range(max_N))
    size_G = list(range(max_N))
    start = 0
    for gsdb in gene_sets_dbfile_list:
        gsdb_split = gsdb.split(".")
        if gsdb_split[-1] == "gmt":
            GSDB = ssGSEAlib.read_genesets_gmt(
                gsdb, thres_min=2, thres_max=2000)
        else:  # is a gmx formatted file
            GSDB = rssGSEAlib.ead_genesets_gmx(
                gsdb, thres_min=2, thres_max=2000)
        N_gs = GSDB['N_gs']
        gs_names[start:(start + N_gs)] = GSDB['gs_names']
        gs_descs[start:(start + N_gs)] = GSDB['gs_desc']
        size_G[start:(start + N_gs)] = GSDB['size_G']
        gs.iloc[start:(start + N_gs), 0:max(GSDB['size_G'])
                       ] = GSDB['gs'].iloc[0:N_gs, 0:max(GSDB['size_G'])]
        start = start + N_gs
    N_gs = max_N

    # Select desired gene sets
    if isinstance(gene_set_selection, list) == False:
        gene_set_selection = gene_set_selection.split(",")
    if gene_set_selection[0].upper() != "ALL":
        locs = list(np.where(np.isin(gs_names, gene_set_selection))[0])
        N_gs = len(locs)
        if N_gs == 0:
            sys.exit("No matches with gene_set_selection")
        elif N.gs > 1:
            gs = gs.iloc[locs]
        else:  # Force vector to matrix if only one gene set specified
            gs = pd.DataFrame(gs.iloc[3]).transpose()
        gs_names=np.array(gs_names)[locs].tolist()
        gs_descs=np.array(gs_descs)[locs].tolist()
        size_G=np.array(size_G)[locs].tolist()

    # Loop over gene sets

    # score_matrix records the enrichment score for each pairing
    # of gene set and sample
    score_matrix=pd.DataFrame(0, index=range(N_gs), columns=range(Ns))
    for gs_i in range(N_gs):
        gene_set=gs.iloc[gs_i, 0:size_G[gs_i]].tolist()
        gene_overlap=list(set(gene_set).intersection(gene_names))
        print(gs_i + 1, "gene set:",
              gs_names[gs_i], " overlap=", len(gene_overlap))
        if len(gene_overlap) < min_overlap:
            # if overlap between gene set and genes in input data set
            # are below a minimum overlap, no enrichment scores are
            # calculated for that gene set.
            score_matrix.iloc[gs_i]=[np.nan] * Ns
            continue
        else:
            gene_set_locs=list(np.where(np.isin(gene_set, gene_overlap))[0])
            gene_names_locs=list(
                np.where(np.isin(gene_names, gene_overlap))[0])
            msig=m.iloc[gene_names_locs]
            msig_names=np.array(gene_names)[gene_names_locs].tolist()
            gs_score=ssGSEAlib.project_to_geneset(
                data_array=m, gene_set=gene_overlap, weight=weight)
            score_matrix.iloc[gs_i]=gs_score["ES_vector"]




# projects gene expression data onto a single
# gene set by calculating the gene set enrichment score
def project_to_geneset(
    # data.matrix containing gene expression data
    data_array,
    # gene set projecting expression data to
    gene_set,
    # exponential weight applied to ranking in calculation of
    # enrichment score
    weight=0):
    import numpy as np

    gene_names=data_array.index.tolist()
    n_rows=data_array.shape[0]
    n_cols=data_array.shape[1]


    ES_vector=[False] * n_cols
    ranked_expression=[0] * n_rows

    # Compute ES score for signatures in each sample
    for sample_index in range(n_cols):
        # gene.list is permutation (list of row indices) of the normalized expression data, where
        # permutation places expression data in decreasing order
        # Note that in ssGSEA we rank genes by their expression level rather than by a measure of correlation
        # between expression profile and phenotype.
        gene_list=(-data_array.iloc[:, sample_index].to_numpy()).argsort()

        # gene.set2 contains the indices of the matching genes.
        # Note that when input GCT file is ATARiS-generated, elements of
        # gene.names may not be unique; the following code insures each element
        # of gene.names that is present in the gene.set is referenced in gene.set2
        gene_set2=np.array(range(len(gene_names)))[
                           list(np.isin(gene_names, gene_set))].tolist()

        # transform the normalized expression data for a single sample into ranked (in decreasing order)
        # expression values
        if weight == 0:
            # don't bother doing calcuation, just set to 1
            ranked_expression=[1] * n_rows
        elif weight > 0:
            # calculate z.score of normalized (e.g., ranked) expression values
            x=data_array.iloc[gene_list, sample_index]
            ranked_expression=(x - np.mean(x)) / np.std(x)

        # tag_indicator flags, within the ranked list of genes, those that are in the gene set
        # notice that the sign is 0 (no tag) or 1 (tag)
        tag_indicator=np.isin(gene_list, gene_set2).astype(int)
        no_tag_indicator=1 - tag_indicator
        N=len(gene_list)
        Nh=len(gene_set2)
        Nm=N - Nh
        # ind are indices into ranked.expression, whose values are in decreasing order, corresonding to
        # genes that are in the gene set
        ind=np.where(tag_indicator == 1)[0]
        ranked_expression=abs(ranked_expression.iloc[ind])**weight

        sum_ranked_expression=sum(ranked_expression)
        # "up" represents the peaks in the mountain plot; i.e., increments in the running-sum
        up=ranked_expression / sum_ranked_expression
        # "gaps" contains the lengths of the gaps between ranked pathway genes
        gaps=(np.append((ind - 1), (N - 1)) - np.insert(ind, 0, -1))
        # "down" contain the valleys in the mountain plot; i.e., the decrements in the running-sum
        down=gaps / Nm
        # calculate the cumulative sums at each of the ranked pathway genes
        RES=np.cumsum(np.append(up, up[Nh - 1]) - down)
        valleys=RES[0:Nh] - up

        max_ES=np.max(RES)
        min_ES=np.min(valleys)

        if max_ES > -min_ES:
            arg_ES=np.argmax(RES)
        else:
            arg_ES=np.argmin(RES)

        # calculates the area under RES by adding up areas of individual
        # rectangles + triangles
        gaps=gaps + 1
        RES=np.append(valleys, 0) * (gaps) + 0.5 * \
                      (np.insert(RES[0:Nh], 0, 0) - \
                       np.append(valleys, 0)) * (gaps)
        ES=sum(RES)
        ES_vector[sample_index]=ES
    return {"ES_vector": ES_vector}
# end of Project.to.GeneSet


# Reimplementation of the R ssGSEA GMT Parser
# Reads a gene set database file (in GMX file format)
# and creates an Pandas Datafrme with each row corresponding to a single
# gene set and containing a list of the gene names making up
# that gene set.  Gene sets that do not satisfy the min and max threshold
# criteria will be filtered out. Returned in a dict with other information
def read_genesets_gmt(gs_db, thres_min=2, thres_max=2000):
    import pandas as pd
    import numpy as np
    with open(gs_db) as f:
        temp=f.read().splitlines()
    max_Ng=len(temp)
    # temp_size_G will contain size of each gene set
    temp_size_G=list(range(max_Ng))
    for i in range(max_Ng):
        temp_size_G[i]=len(temp[i].split("\t")) - 2
    max_size_G=max(temp_size_G)
    gs=pd.DataFrame(np.nan, index=range(max_Ng), columns=range(max_size_G))
    temp_names=list(range(max_Ng))
    temp_desc=list(range(max_Ng))
    gs_count=0
    for i in range(max_Ng):
        gene_set_size=len(temp[i].split("\t")) - 2
        gs_line=temp[i].split("\t")
        gene_set_name=gs_line[0]
        gene_set_desc=gs_line[1]
        gene_set_tags=list(range(gene_set_size))
        for j in range(gene_set_size):
            gene_set_tags[j]=gs_line[j + 2]
        if np.logical_and(gene_set_size >= thres_min, gene_set_size <= thres_max):
            temp_size_G[gs_count]=gene_set_size
            gs.iloc[gs_count]=gene_set_tags + \
                list(np.full((max_size_G - temp_size_G[gs_count]), np.nan))
            temp_names[gs_count]=gene_set_name
            temp_desc[gs_count]=gene_set_desc
            gs_count=gs_count + 1
    Ng=gs_count
    gs_names=list(range(Ng))
    gs_desc=list(range(Ng))
    size_G=list(range(Ng))
    gs_names=temp_names[0:Ng]
    gs_desc=temp_desc[0:Ng]
    size_G=temp_size_G[0:Ng]
    gs.dropna(how='all', inplace=True)
    gs.index=gs_names
    return {'N_gs': Ng, 'gs': gs, 'gs_names': gs_names, 'gs_desc': gs_desc, 'size_G': size_G, 'max_N_gs': max_Ng}


# Reimplementation of the R ssGSEA GMX Parser
# Reads a gene set database file (in GMX file format)
# and creates an Pandas Datafrme with each row corresponding to a single
# gene set and containing a list of the gene names making up
# that gene set.  Gene sets that do not satisfy the min and max threshold
# criteria will be filtered out. Returned in a dict with other information
def read_genesets_gmx(gs_gmx, thres_min=2, thres_max=2000):
    import pandas as pd
    import numpy as np
    df_temp=pd.read_csv(
        gs_gmx, sep='\t', skip_blank_lines=True).transpose().dropna(how='all')
    all_gs_names=df_temp.index.tolist().copy()
    all_gs_desc=df_temp[0].tolist().copy()
    all_gs=df_temp.drop(labels=0, axis=1)
    all_gs_sizes=all_gs.count(axis=1).tolist()
    pass_thresholds=np.logical_and(all_gs.count(
        axis=1) >= thres_min, all_gs.count(axis=1) <= thres_max).to_list()
    gs_names=np.array(all_gs_names)[np.array(
        pass_thresholds)].tolist().copy()
    gs_desc=np.array(all_gs_desc)[np.array(pass_thresholds)].tolist().copy()
    gs_sizes=np.array(all_gs_sizes)[np.array(
        pass_thresholds)].tolist().copy()
    gs=all_gs[pass_thresholds]
    max_Ng=len(all_gs_names)
    Ng=len(gs_names)
    gs.columns=range(len(gs.columns))
    # N_gs = number of gene sets defined in gmx file that satisfy the min and max thresholds
    # gs = matrix containing gene set collections, one per line, satisfying min/max thresholds
    # gs_names = vector of names of gene sets (of length N_gs)
    # gs_desc = vector of descriptions of gene sets (of length N_gs)
    # size_G = vector with sizes of each gene set (of length N_gs)
    # max_N_gs = total number of gene sets defined in gmx file; includes those that do not satisfy min/max thresholds
    return {'N_gs': Ng, 'gs': gs, 'gs_names': gs_names, 'gs_desc': gs_desc, 'size_G': gs_sizes, 'max_N_gs': max_Ng}


# Simple implementation of a GCT parser
# Accepts a GCT file and returns a Pandas Dataframe with a single index
def read_gct(gct):
    import sys
    import pandas as pd
    dataset=pd.read_csv(gct, sep='\t', header=2, index_col=[
        0, 1], skip_blank_lines=True)
    dataset.index.names=["NAME", "Description"]
    dataset_descriptions=dataset.index.to_frame(index=False)
    dataset_descriptions.set_index(["NAME"], inplace=True)
    dataset.index=dataset.index.droplevel(1)  # Drop gene descriptions
    return {'data': dataset, 'row_descriptions': dataset_descriptions["Description"].values}


# Simple implementation of a CHIP Parser for use with ssGSEA
# Reads in a CHIP formatted file and returns a pandas dataframe containing
# the probe to gene mappings
def read_chip(chip):
    import os
    import sys
    import pandas as pd
    chip_df=pd.read_csv(chip, sep='\t', index_col=0, skip_blank_lines=True)
    return chip_df


# Simple implementation of GSEA DEsktop's Collapse Dataset functions for use
# with ssSGEA
# Accepts an expression dataset in GCT format, a CHIP file, and a
# collapse metric and returns a pandas dataframe formatted version of the
# dataset collapsed from probe level to gene level using the specified metric.
def collapse_dataset(dataset, chip, mode="sum"):
    import ssGSEAlib
    import pandas as pd
    if isinstance(dataset, dict) == False:
        dataset=ssGSEAlib.read_gct(dataset)
    if isinstance(chip, pd.DataFrame) == False:
        chip=ssGSEAlib.read_chip(chip)
    if isinstance(dataset, dict) == True:
        dataset=dataset['data']
    joined_df=chip.join(dataset, how='inner')
    joined_df.reset_index(drop=True, inplace=True)
    annotations=joined_df[["Gene Symbol",
                             "Gene Title"]].drop_duplicates().copy()
    joined_df.drop("Gene Title", axis=1, inplace=True)
    if mode == "sum":
        collapsed_df=joined_df.groupby(["Gene Symbol"]).sum()
    if mode == "mean":
        collapsed_df=joined_df.groupby(["Gene Symbol"]).mean()
    if mode == "median":
        collapsed_df=joined_df.groupby(["Gene Symbol"]).median()
    if mode == "max":
        collapsed_df=joined_df.groupby(["Gene Symbol"]).max()
    collapsed_df.index.name="NAME"
    return {'data': collapsed_df, 'row_descriptions': annotations["Gene Title"].values}
