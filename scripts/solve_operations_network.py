import pypsa
import logging
logger = logging.getLogger(__name__)

from solve_network import patch_pyomo_tmpdir, log_memory, solve_network, prepare_network

def set_parameters_from_optimized(n, n_optim):
    lines_typed_i = n.lines.index[n.lines.type != '']
    n.lines.loc[lines_typed_i, 'num_parallel'] = n_optim.lines.loc[lines_typed_i, 'num_parallel']
    lines_untyped_i = n.lines.index[n.lines.type == '']
    for attr in ('s_nom', 'r', 'x'):
        n.lines.loc[lines_untyped_i, attr] = n_optim.lines.loc[lines_untyped_i, attr]
    n.lines['s_nom_extendable'] = False

    links_extend_i = n.links.index[n.links.p_nom_extendable]
    n.links.loc[links_extend_i, 'p_nom'] = n_optim.links['p_nom_opt'].reindex(links_extend_i, fill_value=0.)
    n.links.loc[links_extend_i, 'p_nom_extendable'] = False

    gen_extend_i = n.generators.index[n.generators.p_nom_extendable]
    n.generators.loc[gen_extend_i, 'p_nom'] = n_optim.generators['p_nom_opt'].reindex(gen_extend_i, fill_value=0.)
    n.generators.loc[gen_extend_i, 'p_nom_extendable'] = False

    stor_extend_i = n.storage_units.index[n.storage_units.p_nom_extendable]
    n.storage_units.loc[stor_extend_i, 'p_nom'] = n_optim.storage_units['p_nom_opt'].reindex(stor_extend_i, fill_value=0.)
    n.storage_units.loc[stor_extend_i, 'p_nom_extendable'] = False

    return n

if __name__ == "__main__":
    # Detect running outside of snakemake and mock snakemake for testing
    if 'snakemake' not in globals():
        from vresutils.snakemake import MockSnakemake, Dict
        snakemake = MockSnakemake(
            wildcards=dict(network='elec', simpl='', clusters='45', lv='1.5', opts='Co2L-3H'),
            input=Dict(unprepared="networks/{network}_s{simpl}_{clusters}.nc",
                       optimized="results/networks/{network}_s{simpl}_{clusters}_lv{lv}_{opts}.nc"),
            output=["results/networks/{network}_s{simpl}_{clusters}_lv{lv}_{opts}_op.nc"],
            log=dict(gurobi="logs/s{simpl}_{clusters}_lv{lv}_{opts}_op_gurobi.log",
                     python="logs/s{simpl}_{clusters}_lv{lv}_{opts}_op_python.log")
        )

    tmpdir = snakemake.config['solving'].get('tmpdir')
    if tmpdir is not None:
        patch_pyomo_tmpdir(tmpdir)

    logging.basicConfig(filename=snakemake.log.python,
                        level=snakemake.config['logging_level'])

    n = pypsa.Network(snakemake.input.unprepared)

    n_optim = pypsa.Network(snakemake.input.optimized)
    n = set_parameters_from_optimized(n, n_optim)
    del n_optim

    with log_memory(filename=getattr(snakemake.log, 'memory', None), interval=30., max_usage=True) as mem:
        n = prepare_network(n, solve_opts=snakemake.config['solving']['options'])
        n = solve_network(n, config=snakemake.config['solving'], gurobi_log=snakemake.log.gurobi)

        n.export_to_netcdf(snakemake.output[0])

    logger.info("Maximum memory usage: {}".format(mem.mem_usage[0]))
