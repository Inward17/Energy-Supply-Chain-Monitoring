"""
src/agents/briefing_agent.py
─────────────────────────────
Executive Briefing Agent

Takes deterministic math from the Fixer and SPR agents and uses 
Gemini 2.5 Flash to generate a formal Emergency Action Plan.
"""

import os
from google import genai
from google.genai import types

def generate_emergency_brief(scenario_name, target_refinery, spr_data, reroute_df):
    """
    Takes the deterministic math from the Fixer and SPR agents and uses 
    Gemini to generate a formal Executive Action Plan.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return "⚠️ GEMINI_API_KEY not found. Cannot generate executive brief."

    # Initialize the new Gemini 2.0 SDK client
    client = genai.Client(api_key=api_key)

    # Extract the top recommended route
    top_route = reroute_df.iloc[0] if not reroute_df.empty else None
    
    if top_route is not None:
        route_text = f"Top Recommendation: {top_route['Export Terminal']} ({top_route['Crude Grade']}). Lead Time: {top_route['Lead Time (days)']} days. Landed Cost: {top_route['Landed Cost ($/bbl)']}/bbl."
    else:
        route_text = "CRITICAL FAILURE: No viable alternative routes found."

    # Construct the data context payload for the LLM
    context_payload = f"""
    Current Simulated Crisis: {scenario_name}
    Target Infrastructure: {target_refinery}
    
    SPR Modeler Output:
    - SPR Survival Days: {spr_data['survival_days']}
    - Supply Gap: {spr_data['supply_gap_days']} days
    - Action Recommended: {spr_data['recommendation']}
    - Macro Impact (Est): Inflation {spr_data['macro_infl_impact']}, GDP {spr_data['macro_gdp_impact_pct']}
    
    Procurement Optimizer Output:
    {route_text}
    """

    prompt = f"""
    You are the Chief Intelligence Officer for India's Ministry of Petroleum & Natural Gas.
    Based on the following system outputs, write a brief, urgent, 3-paragraph Emergency Action Plan.
    
    SYSTEM OUTPUTS:
    {context_payload}
    
    FORMATTING RULES:
    1. Paragraph 1: Situation Assessment (Acknowledge the crisis and the SPR vulnerability).
    2. Paragraph 2: Procurement Directive (State exactly where we are buying replacement oil from and the financials).
    3. Paragraph 3: Macro-economic Mitigation (What domestic policies must be activated immediately to survive the supply gap).
    Use a professional, urgent, and highly analytical tone. Do not use markdown headers, just return the paragraphs.
    """

    try:
        # Using gemini-2.5-flash as the fast reasoning engine
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
            )
        )
        return response.text
    except Exception as e:
        return f"⚠️ Error generating brief: {str(e)}"
