# Context: AI-Powered Restaurant Recommendation System

## System Workflow

### Data Ingestion

- Load and preprocess the Zomato dataset from Hugging Face: [ManikaSaini/zomato-restaurant-recommendation](https://huggingface.co/datasets/ManikaSaini/zomato-restaurant-recommendation)
- Extract relevant fields such as restaurant name, location, cuisine, cost, rating, etc.

### User Input

Collect user preferences:

- **Location** (e.g., Delhi, Bangalore)
- **Budget** (low, medium, high)
- **Cuisine** (e.g., Italian, Chinese)
- **Minimum rating**
- **Additional preferences** (e.g., family-friendly, quick service)

### Integration Layer

- Filter and prepare relevant restaurant data based on user input
- Pass structured results into an LLM prompt
- Design a prompt that helps the LLM reason and rank options

### Recommendation Engine

Use the LLM to:

- Rank restaurants
- Provide explanations (why each recommendation fits)
- Optionally summarize choices

### Output Display

Present top recommendations in a user-friendly format:

| Field | Description |
|-------|-------------|
| Restaurant Name | Name of the restaurant |
| Cuisine | Type of cuisine |
| Rating | User or aggregate rating |
| Estimated Cost | Cost for two or similar metric |
| AI-generated explanation | Why this restaurant fits the user's preferences |
