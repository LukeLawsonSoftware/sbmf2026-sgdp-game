import sys
import os
import json
from itertools import combinations, product


def build_source_file(config : dict):
    
    players_defintion = ''.join([f'player a{agent["name"]} a{agent["name"]} endplayer\n' for agent in config['agents']])
    
    resources_defintion = ''.join([f'global r{resource["name"]} : [0..{len(config["agents"])}] init 0;\n' for resource in config['resources']])
    
    resource_failure_rates = ''.join(_build_resource_failure_rates(config))
    
    agent_initialisation = ''.join([f'const int a{agent["name"]}Num = {ctr};\nconst int a{agent["name"]}Goal = {agent["goal"]};\nglobal a{agent["name"]}Done : [0..1] init 0;\n\n' for agent, ctr in zip(config['agents'], range(1, len(config['agents'])+1))])
    
    labels = _build_labels(config)
    
    agent_modules = ''.join([f'{_build_agent_module(agent)}\n\n' for agent in config['agents']])
    
    resource_modules = ''.join([f'{_build_resource_module(config, idx)}\n\n' for idx in range(0, len(config["resources"]))])
    
    reward_structures = _build_reward_structures(config)
    
    return f"""csg

{players_defintion}

{resources_defintion}

{resource_failure_rates}

{agent_initialisation}

{labels}


{agent_modules}


{resource_modules}


{reward_structures}

"""


def _build_resource_failure_rates(resource_config: dict):
    for resource in resource_config['resources']:
        if "failure_rate" in resource:
            yield f'const double r{resource["name"]}Fail = {resource["failure_rate"]};\n'
        else:
            yield f'const double r{resource["name"]}Fail;\n'
            


def _build_labels(config : dict):
    labels = []
    
    # Per agent goal completed
    for agent in config["agents"]:
        labels.append(f'label \"a{agent["name"]}GoalAchieved\" = a{agent["name"]}Done = 1;\n') 
    
    # all agents goal completed
    labels.append(f'label \"allGoalsAchieved\" = ' +  " & ".join([f'a{agent["name"]}Done = 1' for agent in config["agents"]]) + ";\n")
    
    return ''.join(labels)


def _build_agent_module(agent_config : dict):
    
    held_resources_sum = '+'.join([f'(r{resource}=a{agent_config["name"]}Num?1:0)' for resource in agent_config['accessible_resources']])
    less_than_goal_guard = held_resources_sum + f'<a{agent_config["name"]}Goal'
    goal_achieved_guard = held_resources_sum + f'=a{agent_config["name"]}Goal'
    
    idle_action = f'\t[a{agent_config["name"]}_idle] {less_than_goal_guard} -> true;'
    
    request_actions = ''.join([f'\t[a{agent_config["name"]}_req_r{resource}] r{resource}=0 & {less_than_goal_guard} -> true;\n' for resource in agent_config['accessible_resources']])
    
    release_actions = ''.join([f'\t[a{agent_config["name"]}_rel_r{resource}] r{resource}=a{agent_config["name"]}Num & {less_than_goal_guard} -> true;\n' for resource in agent_config['accessible_resources']])

    release_all_action = f'\t[a{agent_config["name"]}_rel_all] {goal_achieved_guard} -> (a{agent_config["name"]}Done\' = 1);'

    return f"""module a{agent_config["name"]}

\t// always able to idle
{idle_action}

\t// request a resource
{request_actions}

\t// release a resource
{release_actions}

\t// release all held resources
{release_all_action}

endmodule"""





def _build_resource_module(config : dict, resource_idx : int):
    
    resource = config["resources"][resource_idx]
    connected_agents = [agent for agent in config["agents"] if resource["name"] in agent["accessible_resources"]]

    # get all possible combinations of requesting agents
    s = [agent["name"] for agent in connected_agents]  
    result = []
    for r in range(len(s) + 1):  
        result.extend(combinations(s, r))


    possibly_concurrent_actions = {}
    for agent in connected_agents:
        agent_actions = []
        agent_name = agent["name"]
        
        # 1. Request actions for any (accessible) resource
        for accessible_resource in agent["accessible_resources"]:
            agent_actions.append(f'a{agent_name}_req_r{accessible_resource}')

        # 2. Release actions for any OTHER (accessible) resource
        for other_resource in agent["accessible_resources"]:
            if other_resource != accessible_resource:
                agent_actions.append(f'a{agent_name}_rel_r{other_resource}')

        # 3. Idle actions
        agent_actions.append(f'a{agent_name}_idle')

        # 4. Release all actions
        agent_actions.append(f'a{agent_name}_rel_all')

        possibly_concurrent_actions[agent_name] = agent_actions

    # Determine Cartesian product of all the lists in possibly_concurrent_actions
    action_combinations = list(product(*possibly_concurrent_actions.values()))
    
    def _is_relevant_lhs(action_combination):
        return any(f'_req_r{resource["name"]}' in action for action in action_combination)

    def _determine_rhs(action_combination):
        competing_agent_full_names = [action.split("_")[0] for action in action_combination if f'_req_r{resource["name"]}' in action]
        num_competing_agents = len(competing_agent_full_names)
        if num_competing_agents > 1:
            return ' + '.join([f'(1-r{resource["name"]}Fail)/{num_competing_agents} : (r{resource["name"]}\'={agent_full_name}Num)' for agent_full_name in competing_agent_full_names]) + f' + r{resource["name"]}Fail : (r{resource["name"]}\'=0);'
        else:
            return f'(1-r{resource["name"]}Fail) : (r{resource["name"]}\'={competing_agent_full_names[0]}Num) + r{resource["name"]}Fail : (r{resource["name"]}\'=0);'

    # Determine RHS for each action combination
    request_actions_list = []
    for action_combination in action_combinations:
        if _is_relevant_lhs(action_combination):
            lhs = '[' + ', '.join(action_combination) + ']'
            rhs = _determine_rhs(action_combination)
            request_actions_list.append(f'\t{lhs} true -> {rhs}\n')
    
    request_actions = ''.join(request_actions_list)
    
    release_actions = ''.join([f'\t[a{agent["name"]}_rel_r{resource["name"]}] true -> (r{resource["name"]}\'=0);\n' for agent in connected_agents])
    
    release_all_actions = ''.join([f'\t[a{agent["name"]}_rel_all] r{resource["name"]}=a{agent["name"]}Num -> (r{resource["name"]}\'=0);\n' for agent in connected_agents])
    
    default_action = f'\t[] true -> 1-r{resource["name"]}Fail : true + r{resource["name"]}Fail : (r{resource["name"]}\'=0);'
    
    
    return f"""module r{resource["name"]}

\t// Possible outcomes if this resource is requested (possible for multiple resources to have requested)
{request_actions}

\t// Outcomes if this resource is released (only possible for one resource to have released)
{release_actions}

\t// Outcomes if this resource is released as part of a 'release all' action
{release_all_actions}

\t// Default action if no action related to this resource
{default_action}

endmodule"""



def _build_reward_structures(config : dict):
    
    reward_structures = []
    
    # Timer reward structure
    timer_reward_structure = 'rewards \"timer\"\n'
    timer_reward_structure += '\t[] true : 1;\n'
    timer_reward_structure += 'endrewards\n\n'
    reward_structures.append(timer_reward_structure)
    
    # Reward structures for agents
    agents = config["agents"]
    
    for agent in agents:
        reward_structure = f'rewards \"a{agent["name"]}_reward\"\n'
        reward_structure += f'\t[a{agent["name"]}_rel_all] true : 1;\n'
        reward_structure += 'endrewards\n\n'
        reward_structures.append(reward_structure)
        
        
    # Total reward structure
    total_reward_structure = 'rewards \"total_reward\"\n'
    for agent in agents:
        total_reward_structure += f'\t[a{agent["name"]}_rel_all] true : 1;\n'
    total_reward_structure += 'endrewards\n\n'
    reward_structures.append(total_reward_structure)

    return ''.join(reward_structures)

def load_config(config_path):
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        print(f"Error: The file at {config_path} is not a valid JSON file.")
        sys.exit(1)
    except Exception as e:
        print(f"Error loading configuration file: {e}")
        sys.exit(1)


def main():
    source_config_file = str(sys.argv[1])
    output_file_name = str(sys.argv[2])

    config = load_config(source_config_file)
    model_source_file = build_source_file(config)
    output_path = output_file_name
    with open(output_path, "w") as out_file:
        out_file.write(model_source_file)
    print(f"PRISM-game source file generated for {source_config_file}")

  

if __name__ == "__main__":
    main()

