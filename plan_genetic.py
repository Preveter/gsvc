from deap import base, creator, tools, algorithms
from random import randint, getrandbits, choice, shuffle, randrange
from plan import WorkPlan
from plan_simple import make_plan as pl_simple


def with_next(iterable):
    iterator = iter(iterable)
    current_item = next(iterator)  # throws StopIteration if empty.
    for next_item in iterator:
        yield (current_item, next_item)
        current_item = next_item
    yield (current_item, None)


def random_plan(cls, machines, tasks):
    wp = cls()
    wp.randomize(machines, tasks)
    return wp


def pseudo_random_plan(cls, machines, tasks, prev_plan):

    use_old_plan = True
    if prev_plan is None or len(machines) != len(prev_plan.chains):
        use_old_plan = False

    for machine in machines:
        if machine.id not in prev_plan.chains:
            use_old_plan = False

    if bool(getrandbits(1)):
        use_old_plan = False

    if use_old_plan:
        wp = prev_plan
        for task in tasks:
            if wp.get_task_pos(task.id) != (-1, -1):
                continue

            m_ids = [m.id for m in machines if m.check_task_clean(task)]
            mid = choice(m_ids)
            if mid in wp.chains:
                chain = wp.chains[mid]
            else:
                chain = wp.create_chain(mid)

            n = len(chain)
            idx = randrange(n) if n > 0 else 0

            chain.insert(idx, task.id)
    else:
        machines = machines[:]
        shuffle(machines)
        wp = cls(pl_simple(machines, tasks))
    return wp


def make_plan_from_parts(cls, parts):
    for part in parts:
        part["pos"] = part["pos1"] if bool(getrandbits(1)) else part["pos2"]
    parts.sort(key=lambda p: p["pos"][1])
    parts.sort(key=lambda p: p["pos"][0])

    child = cls()
    last_chain = -1
    candidates = []
    for part, nxt in with_next(parts):
        if part["pos"][0] != last_chain:
            child.create_chain(part["pos"][0])
            last_chain = part["pos"][0]

        candidates.append(part["data"])

        if nxt is None or part["pos"] != nxt["pos"]:
            shuffle(candidates)
            for c in candidates:
                child.append_to_chain(part["pos"][0], c)
            candidates = []

    return child


def mate(cls, plan1, plan2):
    parts = []

    for mid, chain in plan1.chains.items():
        if len(chain) == 0:
            continue

        tid = chain[0]
        part_data = [tid]
        part_pos_1 = (mid, 0)
        part_pos_2 = plan2.get_task_pos(tid)

        for idx, tid in enumerate(chain[1:]):
            if tid == plan2.get_next_task_id(part_data[-1]):
                part_data.append(tid)
            else:
                parts.append({
                    "data": part_data,
                    "pos1": part_pos_1,
                    "pos2": part_pos_2,
                })
                part_data = [tid]
                part_pos_1 = (mid, idx)
                part_pos_2 = plan2.get_task_pos(tid)

        parts.append({
            "data": part_data,
            "pos1": part_pos_1,
            "pos2": part_pos_2,
        })

    ch1, ch2 = make_plan_from_parts(cls, parts), make_plan_from_parts(cls, parts)

    if ch1.count_tasks() != ch2.count_tasks() or ch1.count_tasks() != plan1.count_tasks():
        print("ВАСЯ ЕСТ НЕНАША")

    return ch1, ch2


def mutate(machines, tasks, plan, max_exchanges, max_moves):
    exchanges = randint(1, max_exchanges) if max_exchanges > 1 else 1
    moves = randint(1, max_moves) if max_moves > 1 else 1

    n = plan.count_tasks()
    if n < 2:
        return plan,

    for i in range(exchanges):

        # Select and find first task
        tid_1, mid_1, idx_1 = plan.get_random_task()
        chain_1 = plan.chains[mid_1]

        machine_1 = None
        for m in machines:
            if m.id == mid_1:
                machine_1 = m
                break

        task_1 = None
        for t in tasks:
            if t.id == tid_1:
                task_1 = t
                break

        if machine_1 is None or task_1 is None:
            raise ValueError

        # Get jobs from machines that can contain task_1
        m_fit = [m for m in machines if m.check_task_clean(task_1)]
        chains_fit = [plan.chains[m.id] for m in m_fit if m.id in plan.chains]
        tid_fit = [task for chain in chains_fit for task in chain]

        # Remove self id from exchange list
        tid_fit.remove(tid_1)

        # Remove tasks that doesn't fit to first machine
        tid_fit_2 = []
        for tid in tid_fit:
            for t in tasks:
                if t.id == tid and machine_1.check_task_clean(t):
                    tid_fit_2.append(tid)

        if len(tid_fit_2) == 0:
            continue
            # TODO: Should i retry exchange?

        # Find second item
        tid_2 = choice(tid_fit_2)
        mid_2, idx_2 = plan.find_task(tid_2)
        chain_2 = plan.chains[mid_2]

        # Replace
        chain_1[idx_1] = tid_2
        chain_2[idx_2] = tid_1

        # Clear fitness caches
        if mid_1 in plan.fitness_cache:
            del plan.fitness_cache[mid_1]
        if mid_2 in plan.fitness_cache:
            del plan.fitness_cache[mid_2]

    for i in range(moves):

        # Select and find task
        tid_1, mid_1, idx_1 = plan.get_random_task()
        chain_1 = plan.chains[mid_1]

        task_1 = None
        for t in tasks:
            if t.id == tid_1:
                task_1 = t
                break

        if task_1 is None:
            raise ValueError

        # Select destination chain
        m_ids = [m.id for m in machines if m.check_task_clean(task_1)]
        mid_2 = choice(m_ids)
        if mid_2 in plan.chains:
            chain_2 = plan.chains[mid_2]
        else:
            chain_2 = plan.create_chain(mid_2)

        # Select exact destination
        n = len(chain_2)
        idx_2 = randrange(n) if n > 0 else 0

        # Move
        del chain_1[idx_1]
        chain_2.insert(idx_2, tid_1)

        # Clear fitness caches
        if mid_1 in plan.fitness_cache:
            del plan.fitness_cache[mid_1]
        if mid_2 in plan.fitness_cache:
            del plan.fitness_cache[mid_2]

    return plan,


def evaluate(machines_all, tasks, plan):

    # Clone active machines
    machines = [machine.clone() for machine in machines_all if machine.id in plan.chains]

    max_time = 0
    sum_cost = 0

    for machine in machines:
        mid = machine.id

        i = 0
        time = 0
        cost = 0

        if mid in plan.fitness_cache:
            time, cost = plan.fitness_cache[mid]
        else:
            next_task = None
            if len(plan.chains[machine.id]) > 0:
                next_task_id = plan.chains[machine.id][0]
                for task in tasks:
                    if task.id == next_task_id:
                        next_task = task

            while True:

                # Trying to run as more jobs as possible
                while next_task is not None:
                    if machine.check_task(next_task):
                        machine.run_task(next_task)
                        i += 1

                        next_task = None
                        try:
                            next_task_id = plan.chains[mid][i]
                        except IndexError:
                            break
                        for task in tasks:
                            if task.id == next_task_id:
                                next_task = task
                    else:
                        break

                # Go
                if not machine.idle:
                    time_shift = min((task["time_left"] for task in machine.workload))
                    for task in machine.workload:
                        task["time_left"] -= time_shift
                        if task["time_left"] <= 0:
                            machine.workload.remove(task)
                    machine.update_free_resources()
                    time += time_shift

                if machine.idle and next_task is None:
                    cost = machine.cost * time
                    plan.fitness_cache[mid] = (time, cost)
                    break

        max_time = max(max_time, time)
        if not machine.fixed:  # Cost for fixed machines depends from max_time, so we calculate it later
            sum_cost += cost

    # Cost for fixed machines
    for machine in machines_all:
        if machine.fixed:
            sum_cost += machine.cost * max_time
    # Should we assume zero cost for fixed machines?

    return max_time, sum_cost


def make_plan(machines, tasks, old_plan):

    creator.create("FitnessMin", base.Fitness, weights=(-1.0, -1.0))
    creator.create("WorkPlan", WorkPlan, fitness=creator.FitnessMin)

    toolbox = base.Toolbox()
    toolbox.register("individual", pseudo_random_plan, creator.WorkPlan, machines, tasks, old_plan)
    toolbox.register("population", tools.initRepeat, list, toolbox.individual)

    toolbox.register("mate", mate, creator.WorkPlan)
    toolbox.register("mutate", mutate, machines, tasks, max_exchanges=1, max_moves=1)
    toolbox.register("select", tools.selTournament, tournsize=3)
    toolbox.register("evaluate", evaluate, machines, tasks)

    NGEN = 1
    MU = 2
    LAMBDA = 2
    CXPB = 0.7
    MUTPB = 0.2

    pop = toolbox.population(n=MU)
    hof = tools.ParetoFront()

    algorithms.eaMuPlusLambda(pop, toolbox, MU, LAMBDA, CXPB, MUTPB, NGEN, halloffame=hof, verbose=False)

    return hof.items[0]
