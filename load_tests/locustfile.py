from uuid import uuid4

from locust import HttpUser, between, task


class AirlineAgentSmokeUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self) -> None:
        self.customer_email = "testcustomer@nyu.edu"
        self.staff_username = "admin"
        self.airline_name = "United"

    @task
    def agent_workflow_smoke(self) -> None:
        self.customer_flight_search()
        self.customer_policy_qa()
        self.staff_review_analysis()
        self.staff_sales_report()
        self.metrics_snapshot()

    def customer_flight_search(self) -> None:
        self._customer_chat("Find flights from SFO to LAX next month", "customer_flight_search")

    def customer_policy_qa(self) -> None:
        self._customer_chat("Can I get a refund if my flight is cancelled?", "customer_policy_qa")

    def staff_review_analysis(self) -> None:
        self._staff_chat("Which flights have the worst reviews?", "staff_review_analysis")

    def staff_sales_report(self) -> None:
        self._staff_chat("Show me the sales report for the last year", "staff_sales_report")

    def metrics_snapshot(self) -> None:
        with self.client.get("/api/metrics", name="GET /api/metrics", catch_response=True) as response:
            if response.status_code != 200:
                response.failure(f"metrics endpoint returned {response.status_code}")

    def _customer_chat(self, message: str, name: str) -> None:
        payload = {
            "session_id": f"locust-{name}-{uuid4()}",
            "customer_email": self.customer_email,
            "message": message,
        }
        with self.client.post("/api/agent/customer/chat", json=payload, name=f"POST /customer/chat {name}", catch_response=True) as response:
            self._validate_agent_response(response)

    def _staff_chat(self, message: str, name: str) -> None:
        payload = {
            "session_id": f"locust-{name}-{uuid4()}",
            "staff_username": self.staff_username,
            "airline_name": self.airline_name,
            "message": message,
        }
        with self.client.post("/api/agent/staff/chat", json=payload, name=f"POST /staff/chat {name}", catch_response=True) as response:
            self._validate_agent_response(response)

    @staticmethod
    def _validate_agent_response(response) -> None:
        if response.status_code != 200:
            response.failure(f"agent endpoint returned {response.status_code}")
            return
        try:
            body = response.json()
        except ValueError:
            response.failure("agent endpoint did not return JSON")
            return
        if not body.get("answer"):
            response.failure("agent response did not include an answer")
        elif "controlled error" in body["answer"].lower():
            response.failure(body["answer"])
