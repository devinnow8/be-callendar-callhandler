from fastapi import FastAPI, Form
from fastapi.responses import Response
from fastapi import APIRouter
from fastapi import FastAPI, HTTPException
import requests


router = APIRouter()

# The list of fields we want to keep
DESIRED_FIELDS = {
    "course_language",
    "center_name",
    "residential_course",
    "complex_timings",
    "course_complex_timing",
    "timezone",
    "currency",
    "course_fee",
    "title",
    "teachers",
    "teachers_info",
    "organizer_info",
    "address",
    "address_short",
    "street_address_1",
    "street_address_2",
    "city",
    "state",
    "zip_postal_code",
    "country",
    "course_id",
    "link",
    "phones",
    "end_date",
    "start_date"
}

API_URL = (
    "https://unity.artofliving.org/csapi/courses?country=de&"
    "ctype=811569,813989,811570,840026,433942,12371,825099,825122,"
    "55116,55116,215602,12415,366379,12410,106815,12463,313048,"
    "313048,308901,384238,308897,393172,764812,12397,370064,387510,"
    "22119,55537,55543,384233,12423,377469,51870,55541,384236,"
    "384237,384237,594182,641796,12427,385302,12422,376073,380278,"
    "106817,384234,409022,408853,384238,368358,377107,234752,"
    "384241,476729,530376,530375,552604,562034,563489,688045,"
    "813989,829560,1043574,1001305,377475,12414,22125,377477,"
    "462520,688045,563489,12430&language=en-de&extend_to_limit=1&"
    "center_id=5797&distance-unit=km&field_childrens=true&offset=1&type=country&"
)

@router.get("/filtered-courses")
def get_filtered_courses():
    # 1. Make the GET request to your existing API
    response = requests.get(API_URL)
    data = response.json()

    # 2. Retrieve the courses array safely
    courses = data.get("courses", [])

    # 3. Filter out only desired fields, omitting "accommodations"
    filtered_courses = []
    for course in courses:
        filtered_course = {}
        for field in DESIRED_FIELDS:
            filtered_course[field] = course.get(field, None)
        filtered_courses.append(filtered_course)

    # 4. Return the filtered data in JSON
    return {"courses": filtered_courses}
