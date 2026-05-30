# Airline AgentOps Policy Knowledge Base

## Baggage Policy
Each passenger may bring one carry-on bag and one personal item in the mock booking environment. Checked baggage rules depend on airline policy and ticket class. The demo system does not calculate real baggage fees.

## Refund Policy
Refund eligibility depends on flight status and ticket rules. For this production-like MVP, a ticket can be treated as refundable in the demo only when the flight is cancelled by the airline. Voluntary refunds are not automatically approved by the agent.

## Delay Policy
If a flight is delayed, the agent may explain the current flight status and direct the customer to staff support. The demo system does not issue real compensation, vouchers, or payment refunds.

## Booking Confirmation Policy
The customer agent cannot directly issue a ticket from a natural-language request. It must first create a PENDING_CONFIRMATION booking intent. A ticket is written to the database only after the customer explicitly confirms the booking.

## Mock Payment Policy
The project never connects to a real payment processor. Confirmed agent bookings use a mock payment token and are intended only for engineering demonstration, testing, and evaluation.

## Agent Safety Policy
Agents must use registered tools for database-backed actions. The LLM is not allowed to execute raw SQL. Staff-only analytics tools cannot be called by customer sessions.

