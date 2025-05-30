# app.py

import json
import os
import re
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS
import random
# Import NLTK for sentiment analysis
import nltk
import ssl
import sys

# Create Flask app
app = Flask(__name__)
CORS(app)

# Get current directory for file operations
current_directory = os.path.dirname(os.path.abspath(__file__))

# Fix SSL issues for NLTK download (common issue)
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context

# Download VADER lexicon directly
print("Downloading VADER lexicon...")
nltk.download('vader_lexicon')
print("Download complete.")

# Import the sentiment analyzer after downloading
try:
    from nltk.sentiment.vader import SentimentIntensityAnalyzer
    sentiment_analyzer = SentimentIntensityAnalyzer()
    print("Sentiment analyzer initialized successfully.")
    
    # Function to analyze sentiment of a text with improved credit card context
    def analyze_sentiment(text):
        if not text or text.strip() == "":
            return {
                "compound": 0,
                "pos": 0.5,
                "neu": 0.5,
                "neg": 0,
                "sentiment": "neutral",
                "emoji": "😐"
            }
        
        # First, get the base sentiment scores from VADER
        scores = sentiment_analyzer.polarity_scores(text)
        compound = scores['compound']
        
        # Credit card review specific analysis
        text_lower = text.lower()
        
        # Define keyword patterns for credit card reviews
        negative_keywords = [
            'annual fee', 'expensive', 'high fee', 'too high', 'drawback', 
            'downside', 'catch', 'problem', 'disappoint', 'not worth', 
            'not happy', 'limited', 'fee', 'fees', 'cost', 'costly',
            'not good', 'not great', 'beware', 'warn', 'caution', 
            'better options', 'better card', 'could be better'
        ]
        
        positive_keywords = [
            'great', 'excellent', 'awesome', 'worth', 'best', 'love', 
            'recommend', 'perfect', 'fantastic', 'amazing', 'valuable',
            'benefits', 'reward', 'cash back', 'points', 'perks', 'no annual fee',
            'free', 'bonus', 'satisfied', 'happy with'
        ]
        
        # Check for mixed sentiment (both positive and negative aspects)
        has_negative = any(keyword in text_lower for keyword in negative_keywords)
        has_positive = any(keyword in text_lower for keyword in positive_keywords)
        
        # Special case for credit card reviews:
        # If the review mentions positive aspects but also mentions fees/drawbacks,
        # it should be considered mixed rather than purely positive
        if has_positive and has_negative:
            # Override the VADER compound score for mixed reviews
            compound = 0  # Neutral compound score for mixed reviews
            sentiment_type = "neutral"
            emoji = "😐"
        elif compound >= 0.05:
            sentiment_type = "positive"
            # Gradation of positive emojis
            if compound >= 0.75:
                emoji = "😍"  # Extremely positive
            elif compound >= 0.5:
                emoji = "😁"  # Very positive
            else:
                emoji = "🙂"  # Moderately positive
        elif compound <= -0.05:
            sentiment_type = "negative"
            # Gradation of negative emojis
            if compound <= -0.75:
                emoji = "😡"  # Extremely negative
            elif compound <= -0.5:
                emoji = "😞"  # Very negative
            else:
                emoji = "😕"  # Moderately negative
        else:
            sentiment_type = "neutral"
            emoji = "😐"  # Neutral

        # Look for specific phrases that indicate conditional positivity
        conditional_phrases = [
            "if you", "for those who", "as long as", "assuming", 
            "provided that", "only if", "when you", "depending on"
        ]
        
        if any(phrase in text_lower for phrase in conditional_phrases) and compound > 0:
            # Reviews with conditional statements are more nuanced
            if compound > 0.5:  # If it was very positive, tone it down
                compound = 0.3  # Make it only slightly positive
                emoji = "🙂"
                sentiment_type = "positive"
            else:
                compound = 0  # Otherwise make it neutral
                emoji = "😐"
                sentiment_type = "neutral"
        
        # Check for specific fee-related phrases that indicate mixed sentiment
        fee_offset_phrases = ["annual fee", "worth the fee", "fee is worth", "justified", "offset"]
        if "fee" in text_lower and any(phrase in text_lower for phrase in fee_offset_phrases):
            # Reviews discussing fee-value tradeoffs are generally mixed
            compound = 0
            emoji = "😐"
            sentiment_type = "neutral"
        
        return {
            "compound": compound,
            "pos": scores["pos"],
            "neu": scores["neu"],
            "neg": scores["neg"],
            "sentiment": sentiment_type,
            "emoji": emoji
        }
        
except Exception as e:
    print(f"Error setting up sentiment analysis: {str(e)}", file=sys.stderr)
    # Fallback function for sentiment analysis if NLTK fails
    def analyze_sentiment(text):
        print("Using fallback sentiment analysis function.")
        # Return a default neutral sentiment
        return {
            "compound": 0,
            "pos": 0.5,
            "neu": 0.5,
            "neg": 0,
            "sentiment": "neutral",
            "emoji": "😐"
        }

# Load the dataset
json_file_path = os.path.join(current_directory, 'dataset', 'dataset.json')
with open(json_file_path, 'r') as file:
    data = json.load(file)

# Pre-extract fields for recommendation math
card_names = [entry["name"] for entry in data]
reviews = [entry.get("our_take_value", "") for entry in data]
categories = [entry.get("category", "") for entry in data]
annual_fees = [entry.get("annual_fee_value", "N/A") for entry in data]
foreign_transaction_fees = [entry.get("foreign_transaction_fee_value", "N/A") for entry in data]
min_credit_scores = [entry.get("credit_score_low", "N/A") for entry in data]
issuers = [entry.get("issuer", "") for entry in data]
user_reviews = ["     ".join(entry.get("user_reviews", [])) for entry in data]
bonus_offers = [entry.get("bonus_offer_value", "") for entry in data]
short_card_names = [entry.get("short_card_name", "") for entry in data]
pros_value = [entry.get("pros_value", "") for entry in data]

# Extract enhanced fields
associated_airlines = [entry.get("associated_airlines", []) for entry in data]
income_tiers = [entry.get("income_tier", "any") for entry in data]
travel_value_scores = [entry.get("travel_value_score", 5.0) for entry in data]

# Print some diagnostics
print(f"Loaded {len(data)} cards.")
print(f"Sample card: {card_names[0]}/{short_card_names[0]} category: {categories[0]} category: {categories[0]}")
print(f"Enhanced fields sample: Airlines: {associated_airlines[0] if associated_airlines[0] else 'None'}, Income tier: {income_tiers[0]}, Travel value: {travel_value_scores[0]}")

# Build TF-IDF + SVD matrices
informed_description = [
    f"{rev} {pros_value[i]} issuer: {issuers[i]} card name: {card_names[i]}/{short_card_names[i]} card name: {card_names[i]}/{short_card_names[i]} card name: {card_names[i]}/{short_card_names[i]} category: {categories[i]} category: {categories[i]}"
    for i, rev in enumerate(reviews)
]

custom_stop_words = set(ENGLISH_STOP_WORDS)
custom_stop_words.update(["card", "want", "credit"])

vectorizer = TfidfVectorizer(stop_words=list(custom_stop_words))
tfidf_matrix_raw = vectorizer.fit_transform(informed_description)
svd = TruncatedSVD(n_components=130, random_state=42)
tfidf_matrix = svd.fit_transform(tfidf_matrix_raw)

user_review_vectorizer = TfidfVectorizer(stop_words=list(custom_stop_words))
user_review_matrix_raw = user_review_vectorizer.fit_transform(user_reviews)
user_svd = TruncatedSVD(n_components=130, random_state=42)
user_review_matrix = user_svd.fit_transform(user_review_matrix_raw)

def filter_by_credit_score(recommendations, credit_score):
    if not credit_score or credit_score == "all" or credit_score == "not_relevant":
        return recommendations

    credit_score_minimums = {
        "excellent": 750,
        "good": 700,
        "fair": 650,
        "poor": 300
    }
    user_min_score = credit_score_minimums.get(credit_score, 0)
    filtered = []

    for rec in recommendations:
        title = rec["title"]
        idx = next((i for i,n in enumerate(card_names) if n == title), -1)
        if idx == -1:
            filtered.append(rec)
            continue

        card_req = min_credit_scores[idx]
        try:
            if card_req in (None, "N/A"):
                filtered.append(rec)
                continue
            if isinstance(card_req, str) and card_req.isdigit():
                card_req = int(card_req)
            if user_min_score >= card_req:
                filtered.append(rec)
        except:
            filtered.append(rec)

    return filtered

def filter_by_annual_fee(recommendations, annual_fee_preference):
    try:
        max_fee = int(annual_fee_preference)
    except (TypeError, ValueError):
        max_fee = 500  

    # Don't filter if user says "Don't care"
    if max_fee == 500:
        return recommendations

    filtered = []

    for rec in recommendations:
        title = rec.get("title", "")
        idx = next((i for i, n in enumerate(card_names) if n == title), -1)
        if idx == -1:
            filtered.append(rec)
            continue

        fee_raw = annual_fees[idx]
        try:
            if fee_raw in (None, "N/A"):
                continue 

            fee_str = str(fee_raw).replace('$', '').strip().lower()
            if "none" in fee_str or fee_str == "0":
                fee_value = 0
            else:
                m = re.search(r'\d+', fee_str)
                fee_value = int(m.group()) if m else float('inf')

            if max_fee == 0:
                if fee_value == 0:
                    filtered.append(rec)
            elif fee_value <= max_fee:
                filtered.append(rec)

        except Exception:
            continue  
    return filtered

def apply_airline_preference(recommendations, airline_preference):
    """Apply a weighted adjustment based on the preferred airline"""
    if not airline_preference or airline_preference == "none" or airline_preference == "not_relevant":
        return recommendations
    
    for rec in recommendations:
        title = rec["title"]
        idx = next((i for i, n in enumerate(card_names) if n == title), -1)
        if idx == -1:
            continue
        
        airline_match = False
        card_airlines = associated_airlines[idx] if idx < len(associated_airlines) else []
        
        if airline_preference.lower() in [airline.lower() for airline in card_airlines]:
            # Direct match with card's airline association
            airline_match = True
            boost_factor = 1.15  # 15% boost
            reason = f"Card is associated with {airline_preference} airline" 
            impact = "+15%"
        elif any(airline_preference.lower() in airline.lower() for airline in card_airlines):
            # Partial match
            airline_match = True
            boost_factor = 1.10  # 10% boost
            reason = f"Card has some benefits for {airline_preference} airline"
            impact = "+10%"
        
        # Apply boost if there's a match
        if airline_match:
            # Store original score for explanation
            original_score = rec["similarity_score"]
            rec["similarity_score"] *= boost_factor
            rec["match_percentage"] = min(int(rec["similarity_score"] * 100), 99)
            
            # Add explanation factor
            if "match_factors" not in rec:
                rec["match_factors"] = []
            
            rec["match_factors"].append({
                "factor": reason,
                "impact": impact,
                "original_score": original_score,
                "new_score": rec["similarity_score"]
            })
    
    return recommendations

def apply_travel_frequency(recommendations, travel_frequency):
    """Apply weighted adjustment based on travel frequency preference"""
    if not travel_frequency or travel_frequency == "dont-consider" or travel_frequency == "not_relevant":
        return recommendations
    
    for rec in recommendations:
        title = rec["title"]
        idx = next((i for i, n in enumerate(card_names) if n == title), -1)
        if idx == -1:
            continue
        
        # Get travel value score and category
        travel_score = travel_value_scores[idx] if idx < len(travel_value_scores) else 5.0
        category = categories[idx].lower() if idx < len(categories) else ""
        
        # Store original score for explanation
        original_score = rec["similarity_score"]
        boost_factor = 1.0
        reason = ""
        
        # Apply different weights based on travel frequency
        is_travel_card = travel_score >= 7.0 or "travel" in category or "miles" in category
        is_cash_back = "cash_back" in category
        
        # Always apply a travel frequency multiplier when selected
        if travel_frequency == "frequent":
            if is_travel_card:
                # Strong boost for travel cards if user travels frequently
                boost_factor = 1.10
                reason = "Travel card is ideal for frequent travelers"
            else:
                # Small boost for non-travel cards
                boost_factor = 1.01
                reason = "Card compatibility with frequent travel habits"
        elif travel_frequency == "occasional":
            if is_travel_card:
                # Moderate boost for travel cards if user travels occasionally
                boost_factor = 1.05
                reason = "Travel card benefits occasional travelers"
            else:
                # Very small boost for non-travel cards
                boost_factor = 1.01
                reason = "Card compatibility with occasional travel"
        elif travel_frequency == "rare":
            if is_travel_card:
                # Very small boost for travel cards with rare travelers
                boost_factor = 1.01
                reason = "Limited travel benefits for rare travelers"
            elif is_cash_back:
                # Small boost for cash back cards for rare travelers
                boost_factor = 1.05
                reason = "Cash back rewards better for those who rarely travel"
            else:
                boost_factor = 1.01
                reason = "Card compatibility with limited travel needs"
        
        # Only apply and explain if there's a meaningful adjustment
        if boost_factor != 1.0:
            rec["similarity_score"] *= boost_factor
            rec["match_percentage"] = min(int(rec["similarity_score"] * 100), 99)
            
            # Add explanation factor
            if "match_factors" not in rec:
                rec["match_factors"] = []
            
            impact = f"+{(boost_factor-1)*100:.0f}%"
            
            rec["match_factors"].append({
                "factor": reason,
                "impact": impact,
                "original_score": original_score,
                "new_score": rec["similarity_score"]
            })
    
    return recommendations

def get_recommendations(user_input, filters=None, offset=0, limit=3):
    if filters is None:
        filters = {}

    # similarity on description
    desc_vec = svd.transform(vectorizer.transform([user_input]))
    review_vec = user_svd.transform(user_review_vectorizer.transform([user_input]))
    desc_sim = cosine_similarity(desc_vec, tfidf_matrix).flatten()
    review_sim = cosine_similarity(review_vec, user_review_matrix).flatten()
    final_sim = 0.7 * desc_sim + 0.3 * review_sim

    sorted_idx = np.argsort(-final_sim)
    matches = []
    for i in sorted_idx:
        sim = float(final_sim[i])
        pct = int(min(sim * 100, 99))
        top_raw_reviews = []
        for rev in data[i].get("user_reviews", []):
            try:
                rv = user_review_vectorizer.transform([rev])
                rv_svd = user_svd.transform(rv)
                score = float(cosine_similarity(review_vec, rv_svd).flatten()[0])
                
                # Apply improved sentiment analysis to each review
                sentiment_data = analyze_sentiment(rev)
                
                top_raw_reviews.append((rev, score, sentiment_data))
            except:
                continue
        top_raw_reviews.sort(key=lambda x: x[1], reverse=True)
        reviews_out = [{"text": r, "score": s, "sentiment": sent} for r, s, sent in top_raw_reviews[:3]]

        match_factors = []
        
        if len(user_input.split()) > 0:
            user_tokens = set(user_input.lower().split())
            card_desc = data[i].get("offer_details_value", "") + " " + data[i].get("rewards_rate_value", "")
            tokens_in_common = []
            words_to_exclude = ["credit", "card", "want"]
            for token in user_tokens:
                if token in card_desc.lower() and len(token) > 3 and token not in words_to_exclude:
                    tokens_in_common.append(token)
            
            if tokens_in_common:
                match_factors.append({
                    "factor": "Keyword match: " + ", ".join(tokens_in_common[:3]),
                    "impact": "Primary match factor"
                })
        
        user_categories = [cat.strip() for cat in user_input.lower().split() if cat.strip() in ["travel", "cash back", "rewards", "miles", "hotel", "dining"]]
        card_cats = categories[i].lower().split(", ")
        matching_cats = [cat for cat in user_categories if any(cat in c for c in card_cats)]
        
        if matching_cats:
            match_factors.append({
                "factor": "Category match: " + ", ".join(matching_cats),
                "impact": "Category alignment"
            })
            
        if associated_airlines[i]:
            for airline in associated_airlines[i]:
                if airline.lower() in user_input.lower():
                    match_factors.append({
                        "factor": f"Airline match: {airline}",
                        "impact": "Airline affiliation"
                    })
                    break

        matches.append({
            "title":                     card_names[i],
            "category":                  categories[i],
            "annual_fee":                annual_fees[i],
            "foreign_transaction_fee_value": foreign_transaction_fees[i],
            "reward_rate_string_2018":   data[i].get("reward_rate_string_2018", ""),
            "intro_apr_check_value":     data[i].get("intro_apr_check_value", ""),
            "similarity_score":          sim,
            "base_score":                sim,  
            "match_percentage":          pct,
            "reviews":                   reviews_out,
            "bonus_offer_value":         bonus_offers[i],
            "image_url":                 data[i].get("image_url", ""),
            "associated_airlines":       associated_airlines[i] if i < len(associated_airlines) else [],
            "income_tier":               income_tiers[i] if i < len(income_tiers) else "any",
            "travel_value_score":        travel_value_scores[i] if i < len(travel_value_scores) else 5.0,
            "match_factors":             match_factors,
            "detailed_metrics": {
                "description_similarity": float(desc_sim[i]),
                "review_similarity": float(review_sim[i]),
                "combined_similarity": float(final_sim[i]),
                "description_weight": 0.7,
                "review_weight": 0.3,
                "svd_dimensions": 130,
                "top_review_scores": [{"score": float(s), "text": r, "sentiment": sent} 
                                     for r, s, sent in top_raw_reviews[:3]]
            }
        })

    if filters.get("creditScore"):
        matches = filter_by_credit_score(matches, filters["creditScore"])
    if filters.get("annualFee"):
        matches = filter_by_annual_fee(matches, filters["annualFee"])
        
    if filters.get("preferredAirline"):
        matches = apply_airline_preference(matches, filters["preferredAirline"])
    if filters.get("travelFrequency"):
        matches = apply_travel_frequency(matches, filters["travelFrequency"])
    
    # Re-sort by adjusted similarity score
    matches.sort(key=lambda x: x["similarity_score"], reverse=True)
    
    # Filter out cards with match percentage less than 10%
    matches = [match for match in matches if match["match_percentage"] >= 10]
    
    total = len(matches)
    return matches[offset:offset+limit], total

@app.route("/")
def home():
    return render_template('base2.html', title="Card Match - Credit Card Recommender")

@app.route("/filter-cards", methods=["POST"])
def filter_cards():
    credit_score = request.form.get('credit-score')
    return render_template('base2.html', title="Card Match - Credit Card Recommender")

@app.route("/recommend", methods=["POST"])
def recommend():
    data_in = request.get_json()
    query = data_in.get("query", "")
    filters = data_in.get("filters", {})
    offset = data_in.get("offset", 0)
    limit = data_in.get("limit", 3)

    if not query:
        return jsonify({"error": "No query provided"}), 400
    
    recs, total = get_recommendations(query, filters, offset, limit)
    return jsonify({
        "recommendations": recs,
        "pagination": {
            "offset": offset,
            "limit": limit,
            "total": total,
            "has_more": (offset + limit) < total
        }
    })

@app.route('/card-catch')
def card_catch():
    """Renders the Card Catch game page"""
    return render_template('card_catch.html')

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)